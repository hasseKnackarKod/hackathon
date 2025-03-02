# LINC API
import hackathon_linc as lh
import pandas as pd
import numpy as np
import time
import shared
from scipy.optimize import minimize
from functions.metrics import calculate_moving_average
from logger import setup_logger
logger = setup_logger('markowitz', 'logs/markowitz.log')

def markowitz(starting_capital: float):
    logger.info(f"Starting Markowitz strategy with ${starting_capital:,.2f}...")

    data_empty = True
    while data_empty:
        df_daily = pd.DataFrame(shared.shared_data.get('df_daily', pd.DataFrame()).copy())
        if df_daily.empty:
            logger.error("Initial df_daily is empty! Waiting for data...")
            data_empty = True
        else:
            data_empty = False
    
    # Variables
    symbols = list(df_daily['symbol'].unique())
    n_assets = len(symbols)
    current_position = {symbol: 0 for symbol in symbols}
    current_cash = starting_capital
    current_portfolio_value = 0
    starting_date = df_daily['date'].unique().max() if not df_daily.empty else None
    has_position = False

    # Optimization parameters
    w0 = np.ones(n_assets) / n_assets
    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1}) # Weights sum to 1
    bounds = [(0, 1)] * n_assets # Weights between 0 and 1 (no short selling)
    rebalance_days = 21
    risk_aversion = 1.5
    market_breadth_threshold = 0.5
    ma_short = 63
    ma_long = 252

    while True:
        if data_empty:
            logger.error("df_daily is empty! Waiting for data...")
            time.sleep(8) # Wait a day
            continue
        try:
            latest_prices = df_daily.sort_values(by='date').groupby('symbol').last()['closePrice']
            trading_dates = df_daily['date'].unique()

            # **Sell all current positions**
            total_sell = 0
            for symbol, amount in current_position.items():
                if amount > 0:
                    try:
                        sell_response = lh.sell(ticker=symbol, amount=amount)
                        if sell_response.get('order_status') == 'completed':
                            total_sell += amount * sell_response['price']
                        else:
                            logger.warning(f"Sell order for {symbol} failed. Order status: {sell_response.get('order_status', 'unknown')}")
                    except Exception as e:
                        logger.error(f"Error selling {symbol}: {e}")

            has_position = False
            current_cash += total_sell
            current_portfolio_value -= total_sell
            logger.info(f"Sold stocks worth ${total_sell:,.2f}")

            # Calculate moving averages
            df_daily = calculate_moving_average(df_daily, ma_short)
            df_daily = calculate_moving_average(df_daily, ma_long)
            latest_ma = df_daily.sort_values(by='date').groupby('symbol').last()[[f'MA{ma_short}', f'MA{ma_long}']]

            # Calculate market breadth
            market_breadth = (latest_ma[f'MA{ma_short}'] - latest_ma[f'MA{ma_long}'] > 0).sum() / n_assets
            logger.info(f"Current market breadth: {market_breadth}")

            if market_breadth > market_breadth_threshold:
                df_daily['log_return'] = df_daily.groupby('symbol', group_keys=False)['openPrice'].transform(lambda x: np.log(x / x.shift(1)))
                df_daily.dropna(inplace=True)
                df_returns = df_daily.pivot(index='date', columns='symbol', values='log_return')

                if df_returns.empty:
                    logger.warning("No valid return data. Skipping this cycle.")
                    continue  

                current_prices = df_daily[df_daily['date'] == trading_dates[-1]].set_index('symbol')['openPrice']
                past_prices = df_daily[df_daily['date'] == trading_dates[-ma_short]].set_index('symbol')['openPrice']

                valid_assets = current_prices.index.intersection(past_prices.index)
                mu = (current_prices.loc[valid_assets] / past_prices.loc[valid_assets] - 1).values
                Sigma = df_returns.cov().values

                def objective(w, mu, Sigma, risk_aversion):
                    return - (np.dot(w, mu) - risk_aversion * np.dot(w.T, np.dot(Sigma, w)))

                result = minimize(objective, w0, args=(mu, Sigma, risk_aversion), method='SLSQP', bounds=bounds, constraints=constraints)
                optimal_weights = result.x

                # Buying stocks
                stocks_price_budget = current_cash * optimal_weights
                total_buy = 0
                for symbol, price_budget in zip(list(df_returns.columns), stocks_price_budget):
                    amount = int(price_budget / latest_prices[symbol])

                    if amount > 0:
                        try:
                            buy_response = lh.buy(ticker=symbol, amount=amount)
                            if buy_response.get('order_status') == 'completed':
                                current_position[symbol] = amount
                                total_buy += amount * buy_response['price']
                                has_position = True
                            else:
                                logger.warning(f"Buy order for {symbol} failed. Order status: {buy_response.get('order_status', 'unknown')}")
                        except Exception as e:
                            logger.error(f"Error buying {symbol}: {e}")

                current_cash -= total_buy
                current_portfolio_value += total_buy
                logger.info(f"Bought stocks worth ${total_buy:,.2f}")

            logger.info('==================== MARKOVITZ CURRENT STATS ====================')
            logger.info(f"Liquid capital: ${current_cash:,.2f}")
            logger.info(f"Portfolio value: ${current_portfolio_value:,.2f}")
            logger.info(f"Return since {starting_date}: {(current_cash + current_portfolio_value - starting_capital) / starting_capital:.2%}")

            # Wait for rebalance or one day if no current position
            if has_position:
                time.sleep(rebalance_days * 8)
            else:
                time.sleep(8)

            # Update df_daily
            df_daily = pd.DataFrame(shared.shared_data.get('df_daily', pd.DataFrame()).copy())
            data_empty = df_daily.empty

        except Exception as e:
            logger.error(f"Unexpected error in Markowitz strategy: {e}")
            time.sleep(8) # Wait a day
