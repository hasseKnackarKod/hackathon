import hackathon_linc as lh
import pandas as pd
import time
import shared
from functions.metrics import calculate_rsi, calculate_moving_average, calculate_moving_std
from logger import setup_logger
logger = setup_logger('divergence', 'logs/divergence.log')

class DivergenceModel:
    def __init__(self, starting_capital):
        self.starting_capital = starting_capital
        self.cash_capital = starting_capital
        self.portfolio = {}  # {symbol: {'quantity': X, 'buy_price': Y}}
        self.portfolio_value = 0
        self.transaction_log = []
        self.holding_period = 63
        self.cool_down_period = 8 * 21
        self.market_regime_threshold = 0.5
        self.RSI_threshold = 30
        self.std_threshold = 1.5
        self.last_trade_time = {}
        self.cant_buy_timer = {}
        self.live_data = None
        self.daily_data = None

        logger.info(f"DivergenceModel initialized with starting capital: ${starting_capital:,.2f}")

    def update_data(self):
        """Fetches new data every second."""
        data_empty = True
        while data_empty:
            self.live_data = pd.DataFrame(shared.shared_data.get('df', pd.DataFrame()).copy())
            self.daily_data = pd.DataFrame(shared.shared_data.get('df_daily', pd.DataFrame()).copy())
            if self.live_data.empty or self.daily_data.empty:
                logger.error("Initial dfs are empty! Waiting for data...")
                time.sleep(8) # Wait a day
                data_empty = True
            else:
                data_empty = False

        # Maintain rolling window
        max_days = 270
        max_hours = 270 * 8.5
        if len(self.daily_data['date'].unique()) > max_days:
            self.daily_data = self.daily_data.iloc[-max_days:]
        if len(self.live_data['date'].unique()) > max_hours:
            self.live_data = self.live_data.iloc[-max_hours:]

        self.live_data = calculate_rsi(self.live_data, period=17)
        self.daily_data = calculate_moving_average(self.daily_data, period=63)
        self.daily_data = calculate_moving_average(self.daily_data, period=252)
        self.daily_data = calculate_moving_std(self.daily_data, period=63)

        logger.info("Market data updated successfully.")


    def calculate_market_regime(self):
        """Determines whether market conditions allow trading."""
        try:
            latest_daily_date = self.daily_data['date'].max()
            latest_daily_data = self.daily_data[self.daily_data['date'] == latest_daily_date]

            market_breadth = (latest_daily_data['closePrice'] - latest_daily_data['MA63'] > 0).sum() / len(self.daily_data['symbol'].unique())
            market_regime = market_breadth >= self.market_regime_threshold

            logger.info(f"Market Regime Status: {'Active' if market_regime else 'Inactive'}")
            return market_regime
        except Exception as e:
            logger.error(f"Error calculating market regime: {e}")
            return False

    def trade_logic(self):
        """Executes buy/sell decisions based on model."""

        try:
            current_time = self.live_data['gmtTime'].max()
            logger.info(f"Running trade logic at {current_time}")

            buy_candidates = []
            stock_volatilities = {}
            total_risk_weight = 0

            for symbol in self.live_data['symbol'].unique():
                try:
                    latest_row = self.live_data[
                        (self.live_data['symbol'] == symbol) & (self.live_data['gmtTime'] == current_time)
                    ]
                    current_price = latest_row['price']
                    current_RSI = latest_row['RSI17']

                    past_data = self.live_data[(self.live_data['symbol'] == symbol)].iloc[-30:-5]
                    lowest_price = past_data['price'].min()
                    lowest_RSI = past_data['RSI17'].min()

                    latest_daily_prices = self.daily_data[self.daily_data['symbol'] == symbol]
                    prev_daily_data = latest_daily_prices[latest_daily_prices['date'] == self.daily_data['date'].max()]

                    prev_price = prev_daily_data['closePrice']
                    prev_MA63 = prev_daily_data['MA63']
                    prev_STD63 = prev_daily_data['STD63']

                    last_trade = self.cant_buy_timer.get(symbol, 0)
                    if last_trade != 0 and (current_time - last_trade).days < self.cool_down_period:
                        continue

                    if (symbol not in self.portfolio and
                        lowest_RSI < self.RSI_threshold and
                        current_RSI > lowest_RSI and
                        current_price < lowest_price and
                        prev_price > prev_MA63 and
                        self.cash_capital > 0):
                        
                        buy_candidates.append(symbol)
                        stock_volatilities[symbol] = 1 / (prev_STD63 + 1e-6)
                        total_risk_weight += stock_volatilities[symbol]

                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")

            if buy_candidates and self.cash_capital > 0:
                daily_spend_limit = 0.9 * self.cash_capital
                total_allocated = 0

                for symbol in buy_candidates:
                    risk_weight = 1 / len(buy_candidates)
                    bet_size = daily_spend_limit * risk_weight

                    if bet_size > self.cash_capital - total_allocated:
                        bet_size = self.cash_capital - total_allocated

                    if bet_size < 0.01 * self.cash_capital:
                        continue

                    latest_price = self.live_data[self.live_data['gmtTime'].max()]['price']
                    quantity = int(bet_size / latest_price)

                    if quantity > 0:
                        buy_response = lh.buy(ticker=symbol, amount=quantity)
                        if buy_response.get('order_status') == 'completed':
                            latest_price = buy_response['price']
                            self.portfolio[symbol] = {'quantity': quantity, 'buy_price': latest_price}
                            total_allocated += quantity * latest_price
                            self.last_trade_time[symbol] = current_time
                            logger.info(f"Bought {quantity} shares of {symbol} at {latest_price:.2f}")

                self.cash_capital -= total_allocated
                self.portfolio_value += total_allocated

            logger.info(f"Cash Capital: ${self.cash_capital:,.2f}, Portfolio Value: ${self.portfolio_value:,.2f}, Total: ${self.cash_capital + self.portfolio_value:,.2f}")
        except Exception as e:
            logger.error(f"Error in trade logic: {e}")

    def run(self):
        """Runs the live trading loop."""
        while True:
            try:
                self.update_data()
                self.trade_logic()
                time.sleep(1) # Wait one hour
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
