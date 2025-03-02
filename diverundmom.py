import hackathon_linc as lh
import pandas as pd
import numpy as np
import time
from datetime import datetime
import shared
from functions.metrics import calculate_rsi, calculate_moving_average, calculate_moving_std

class LiveTradingModel:
    def __init__(self, starting_capital):
        # Trading parameters
        self.starting_capital = starting_capital
        self.cash_capital = starting_capital
        self.portfolio = {}  # {symbol: {'quantity': X, 'buy_price': Y}}
        self.portfolio_value = 0
        self.transaction_log = []  # Stores trade history
        self.holding_period = 63 # ADJUST
        self.cool_down_period = 8 * 21 # ADJUST 
        self.market_regime_threshold = 0.5
        self.RSI_threshold = 30
        self.std_threshold = 1.5
        self.last_trade_time = {}  # {symbol: timestamp}
        self.cant_buy_timer = {}  # {symbol: timestamp}
        self.live_data = None
        self.daily_data = None

    def update_data(self):
        """Fetches new data every second."""
        self.live_data = shared.shared_data['df'].copy()
        self.daily_data = shared.shared_data['df_daily'].copy()

        # **Maintain rolling window**
        max_days = 270
        max_hours = 270*8.5
        if len(self.daily_data['date'].unique()) > max_days:
            self.daily_data = self.daily_data.iloc[-max_days:]
        if len(self.live_data['date'].unique()) > max_hours:
            self.live_data = self.live_data.iloc[-max_hours:]

        self.live_data = calculate_rsi(self.live_data, period=17) # length of rsi period
        self.daily_data = calculate_moving_average(self.daily_data, period = 63) # length of short moving average period
        self.daily_data = calculate_moving_average(self.daily_data, period = 252) # length of long moving average period

        
        self.daily_data = calculate_moving_std(self.daily_data, period = 63) 


    def calculate_market_regime(self):
        """Determines whether market conditions allow trading."""
        latest_daily_date = self.daily_data['date'].max()
        latest_daily_data = self.daily_data[self.daily_data['date'] == latest_daily_date]
        
        market_breadth = (latest_daily_data['closePrice'] - latest_daily_data['MA63'] > 0).sum()/len(self.daily_data['symbol'].unique())
        #market_breadth = (latest_daily_data["MA63"] - latest_daily_data["MA252"] > 0 ).sum()/len(self.daily_data['symbol'].unique())
        market_regime = market_breadth >= self.market_regime_threshold
        print('=========== MARKET REGIME ================') 
        print(market_regime)
        return market_regime

        # for symbol in latest_daily_data['symbol'].unique():
        #     try:
        #         prev_price = latest_daily_data["priceClose"]           ## DENNA BEHÖVER BYTAS NAMN PÅ MILTON HETER DEN PRICE
        #         prev_MA63 = latest_daily_data["MA_63"]             ## DENNA BEHÖVER BYTAS NAMN PÅ
        #         prev_MA252 = latest_daily_data["MA_252"]           # SKA nog också bytas namn på

        #         if prev_MA63 > prev_MA252:
        #             stock_counter += 1
        #     except KeyError:
        #         continue

        # market_breadth = stock_counter / len(self.daily_data['symbol'].unique()) # Proportion of stocks with positive momentum
        # return market_breadth >= self.market_regime_threshold

    def trade_logic(self):
        """Executes buy/sell decisions based on model."""
        if self.live_data is None or self.daily_data is None:
            return

        current_time = self.live_data['gmtTime'].max()
        # market_condition = self.calculate_market_regime()
        print(f"Dagens datum divergence: {current_time}")

        buy_candidates = []
        stock_volatilities = {}
        total_risk_weight = 0  # To normalize allocations

        for symbol in self.live_data['symbol'].unique():
            try:
                
                
                # Get latest price and RSI
                #latest_row = self.live_data[self.live_data['symbol'] == symbol].iloc[-1]
                latest_row = self.live_data[(self.live_data['symbol'] == symbol) & (self.live_data['gmtTime'] == self.live_data['gmtTime'].max())]
                current_price = latest_row['price']

                #current_price = latest_row['price']
                # current_RSI = self.live_data.loc[self.live_data['gmtTime'].max(), 'RSI17']
                current_RSI = latest_row['RSI17']

                # Historical price and RSI
                past_data = self.live_data[(self.live_data['symbol'] == symbol)].iloc[-30:-5]
                lowest_price = past_data['price'].min()
                lowest_RSI = past_data['RSI17'].min()

                # Daily indicators
                # latest_prices = self.live_data[self.live_data['symbol'] == symbol]
                latest_daily_prices = self.daily_data[self.daily_data['symbol'] == symbol]

                #prev_daily_data = self.daily_data[self.daily_data['symbol'] == symbol].iloc[-1]
                prev_daily_data = latest_daily_prices[latest_daily_prices['date'] == self.daily_data['date'].max()]
                
                prev_price = prev_daily_data['closePrice'] ### ÄNDRAS EFTER RSI PERIOD ==========================================
                prev_MA63 = prev_daily_data['MA63']
                # prev_MA252 = prev_daily_data['MA252'] 
                prev_STD63 = prev_daily_data['STD63'] ## ÄNDRA EFTER RSI PERIOD ==========================================

                # Check if stock is in a cool-down period
                last_trade = self.cant_buy_timer.get(symbol, 0)
                
                
                if last_trade != 0:
                    if (current_time - last_trade).days < self.cool_down_period:
                        continue

                # Buy Condition
                if (
                    # market_condition
                    symbol not in self.portfolio  # Only buy if not already holding
                    and lowest_RSI < self.RSI_threshold # Hour
                    and current_RSI > lowest_RSI # Hour
                    and current_price < lowest_price # Hour 
                    and prev_price > prev_MA63 # EOD
                    and self.cash_capital > 0  # Ensure funds
                ):
                    buy_candidates.append(symbol)
                    stock_volatilities[symbol] = 1 / (prev_STD63 + 1e-6)  # Lower volatility → higher allocation
                    total_risk_weight += stock_volatilities[symbol]

                # Stop-Loss Sell
                elif symbol in self.portfolio:
                    entry_price = self.portfolio[symbol]['buy_price']
                    quantity = self.portfolio[symbol]['quantity']
                    stop_loss_price = entry_price * (1 - self.std_threshold * prev_STD63 / prev_price)

                    if current_price < stop_loss_price:
                        sell_response = lh.sell(ticker=symbol, amount=quantity)    
                        if 'order_status' in sell_response and sell_response['order_status'] == 'completed': # If successful trade
                            self.cash_capital += quantity * sell_response['price']
                            self.portfolio_value -= quantity * sell_response['price']
                            print(f"Stop-loss: Divergence sold {symbol} at {sell_response['price']:.2f}")
                            
                            # Calculate stop-loss loss
                            stop_loss_loss_pct = sell_response['price']/entry_price
                            stop_loss_loss = (sell_response['price'] - entry_price)*quantity
                            print(f"Stop-loss: Loss for {symbol}: {100*(1-stop_loss_loss_pct):.2f}%, (${stop_loss_loss:,.2f})")

                            del self.portfolio[symbol]
                            self.cant_buy_timer[symbol] = current_time

                    # Profit-taking sell
                    elif (current_time - self.last_trade_time[symbol]).days > self.holding_period:
                        sell_response = lh.sell(ticker=symbol, amount=quantity)  
                        if sell_response['order_status'] == 'completed': 
                            self.cash_capital += quantity * sell_response['price']
                            self.portfolio_value -= quantity * sell_response['price']

                            # profit calculation
                            profit_pct = sell_response['price']/entry_price
                            profit = (sell_response['price'] - entry_price)*quantity
                            print(f"Profit-taking: Divergence sold {symbol} at {current_price:.2f}")
                            print(f"Profit-taking: Profit for {symbol}: {100*(1-profit_pct):.2f}%, (${profit:,.2f})")

                            del self.portfolio[symbol]
                            self.cant_buy_timer[symbol] = current_time

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                
        # Step 2: Allocate capital based on risk level and execute trades
        if buy_candidates and self.cash_capital > 0:
            daily_spend_limit = 0.9 * self.cash_capital  # 90% of available cash per day
            total_allocated = 0

            for symbol in buy_candidates:   ## CHANGE AND ADJUST AS WE SEE FIT. Good idea to not be fully invested all time?
                # risk_weight = stock_volatilities[symbol] / total_risk_weight
                risk_weight = 1/len(buy_candidates)
                bet_size = daily_spend_limit * risk_weight  # Allocate based on volatility
                if bet_size > self.cash_capital - total_allocated:
                    bet_size = self.cash_capital - total_allocated  # Ensure we don't overspend

                if bet_size < 0.01 * self.cash_capital:  # Ignore too-small bets
                    continue

                #latest_price = self.live_data[self.live_data['symbol'] == symbol].iloc[-1]['price']
                latest_price = self.live_data[self.live_data['gmtTime'].max(), 'price']
                quantity = int(bet_size / latest_price)

                if quantity > 0:
                    buy_response = lh.buy(ticker=symbol, amount=quantity)
                    if 'order_status' in buy_response and buy_response['order_status'] == 'completed': # If successful trade
                        latest_price = buy_response['price']
                        print('========= TEST =======')
                        print(latest_price)
                        print(quantity)
                        self.portfolio[symbol] = {'quantity': quantity, 'buy_price': latest_price}
                        total_allocated += quantity*latest_price
                        self.last_trade_time[symbol] = current_time
                        print(f"Divergence bought {quantity} shares of {symbol} at {latest_price:.2f}")


            self.cash_capital -= total_allocated  # Deduct total allocated funds
            self.portfolio_value += total_allocated

        # Print current cash and portfolio
        print('====================DIVERGENCE CURRENT STATS ====================')
        print(f"Divergence current liquid capital: ${self.cash_capital:,.2f}")
        print(f"Divergence current portfolio value: ${self.portfolio_value:,.2f}")
        print(f"Divergence total value: ${self.cash_capital + self.portfolio_value:,.2f}, starting balance ${self.starting_capital:,.2f}")
        print(f"Performance {((self.cash_capital + self.portfolio_value)/self.starting_capital):,.2f}")


    def run(self):
        """Runs the live trading loop."""
        while True:
            self.update_data()
            self.trade_logic()
            time.sleep(5)  # Wait 5 hours before next run
