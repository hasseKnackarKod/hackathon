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
        self.transaction_log = []  # Stores trade history
        self.holding_period = 20 # ADJUST
        self.cool_down_period = 8 * 10 # ADJUST 
        self.market_regime_threshold = 0.4
        self.RSI_threshold = 50
        self.std_threshold = 1.0
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

        self.daily_data = calculate_rsi(self.daily_data, period=63)
        self.daily_data = calculate_moving_average(self.daily_data, period = 63)
        self.daily_data = calculate_moving_average(self.daily_data, period = 252) 

        
        self.daily_data = calculate_moving_std(self.daily_data, period = 63) ## UPPDATERA PERIODERNA OCH LÄGG TILL FUNKTIONER SÅ DE blir rättly_data)


    def calculate_market_regime(self):
        """Determines whether market conditions allow trading."""
        stock_counter = 0
        latest_daily_data = self.daily_data.iloc[-1]

        for symbol in self.daily_data['symbol'].unique():
            try:
                prev_price = latest_daily_data[f"{symbol}_close"]
                prev_MA63 = latest_daily_data[f"{symbol}_MA63"]
                prev_MA252 = latest_daily_data[f"{symbol}_MA252"]

                if prev_MA63 > prev_MA252:
                    stock_counter += 1
            except KeyError:
                continue

        market_breadth = stock_counter / len(self.daily_data['symbol'].unique())
        return market_breadth >= self.market_regime_threshold

    def trade_logic(self):
        """Executes buy/sell decisions based on model."""
        if self.live_data is None or self.daily_data is None:
            return

        current_time = self.live_data['timestamp'].iloc[-1]
        market_condition = self.calculate_market_regime()

        buy_candidates = []
        stock_volatilities = {}
        total_risk_weight = 0  # To normalize allocations

        for symbol in self.live_data['symbol'].unique():
            try:
                # Get latest price and RSI
                latest_row = self.live_data[self.live_data['symbol'] == symbol].iloc[-1]
                current_price = latest_row['close']
                current_RSI = latest_row['RSI']

                # Historical price and RSI
                past_data = self.live_data[(self.live_data['symbol'] == symbol)].iloc[-30:-10]
                lowest_price = past_data['close'].min()
                lowest_RSI = past_data['RSI'].min()

                # Daily indicators
                prev_daily_data = self.daily_data[self.daily_data['symbol'] == symbol].iloc[-1]
                prev_price = prev_daily_data['AS TILL'] 
                prev_MA63 = prev_daily_data['MA63']
                prev_MA252 = prev_daily_data['MA252']
                prev_STD63 = prev_daily_data['STD63'] ## ÄNDRA EFTER RSI PERIOD ==========================================

                # Check if stock is in a cool-down period
                last_trade = self.cant_buy_timer.get(symbol, 0)
                if current_time - last_trade < self.cool_down_period:
                    continue

                # Buy Condition
                if (
                    market_condition
                    and symbol not in self.portfolio  # Only buy if not already holding
                    and current_RSI < self.RSI_threshold
                    and current_RSI > lowest_RSI
                    and current_price < lowest_price
                    and prev_price > prev_MA63
                    and prev_MA63 > prev_MA252
                    and self.cash_capital > 0  # Ensure sufficient funds
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
                        lh.sell(ticker=symbol, amount=quantity)                               ### MÅSTE eveneutellt se ifall den vill gå igenomu
                        self.cash_capital += quantity * current_price
                        print(f"Stop-loss: Sold {symbol} at {current_price:.2f}")

                        del self.portfolio[symbol]
                        self.cant_buy_timer[symbol] = current_time

                    # Profit-taking sell
                    elif current_time - self.last_trade_time[symbol] > self.holding_period:
                        lh.sell(ticker=symbol, amount=quantity)                        ### MÅSTE eveneutellt se ifall den vill gå igenom
                        self.cash_capital += quantity * current_price
                        print(f"Profit-taking: Sold {symbol} at {current_price:.2f}")

                        del self.portfolio[symbol]
                        self.cant_buy_timer[symbol] = current_time

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                
        # Step 2: Allocate capital based on risk level and execute trades
        if buy_candidates and self.cash_capital > 0:
            daily_spend_limit = 0.5 * self.cash_capital  # 50% of available cash per day
            total_allocated = 0

        for symbol in buy_candidates:   ## CHANGE AND ADJUST AS WE SEE FIT. Good idea to not be fully invested all time?
            risk_weight = stock_volatilities[symbol] / total_risk_weight
            bet_size = daily_spend_limit * risk_weight  # Allocate based on volatility
            if bet_size > self.cash_capital - total_allocated:
                bet_size = self.cash_capital - total_allocated  # Ensure we don't overspend

            if bet_size < 0.01 * self.cash_capital:  # Ignore too-small bets
                continue

            latest_price = self.live_data[self.live_data['symbol'] == symbol].iloc[-1]['close']
            quantity = int(bet_size / latest_price)

            if quantity > 0:
                lh.buy(ticker=symbol, amount=quantity)

                self.portfolio[symbol] = {'quantity': quantity, 'buy_price': latest_price}
                total_allocated += bet_size
                self.last_trade_time[symbol] = current_time
                print(f"Bought {quantity} shares of {symbol} at {latest_price:.2f}")
            
        self.cash_capital -= total_allocated  # Deduct total allocated funds

    def run(self):
        """Runs the live trading loop."""
        while True:
            self.update_data()
            self.trade_logic()
            time.sleep(1)  # Kanske inte ens behövs?


# Initialize and run the trading model
starting_capital = 100000  # Example starting capital
model = LiveTradingModel(starting_capital)
model.run()
