# LINC API
import hackathon_linc as lh
# Might not be needed:
# lh.init('92438482-5598-4e17-8b34-abe17aa8f598') # Authenticate and connect to API

# For data handling
import pandas as pd
import numpy as np
from datetime import datetime, time

# For plotting
import hvplot.pandas
import holoviews as hv

# For shared data
import shared

# Miscellaneous
import time
from scipy.optimize import minimize
from functions.metrics import calculate_rsi, calculate_moving_average, calculate_moving_std


def markowitz(starting_capital: float):

    # Initialize variables
    df_daily = shared.shared_data['df_daily'].copy()
    symbols = list(df_daily['symbol'].unique())
    n_assets = len(symbols)
    current_position = {symbol: 0 for symbol in symbols} # Symbol : amount
    current_cash = starting_capital
    current_portfolio_value = 0
    starting_date = df_daily['date'].unique().max()
    HAS_POSITION = False

    # Optimization parameters
    w0 = np.ones(n_assets) / n_assets # Initial guess: Equal weights
    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1}) # Constraints: Sum of weights = 1
    bounds = [(0, 1)] * n_assets # Bounds: Ensure weights are non-negative (no short selling)

    # Choose parameters
    # rolling_window = 252  # Rolling window size (1 year)
    rebalance_days = 21   # Rebalance every 21 trading days (monthly)
    risk_aversion = 1.5  # Risk aversion parameter
    market_breadth_threshold = 0.5 # Increase for harsher threshold
    ma_short = 63
    ma_long = 252

    print(f"Markowitz got starting capital: ${starting_capital:,.2f}")
    
    while True:
        # Get latest prices
        latest_prices = df_daily.sort_values(by='date').groupby('symbol').last()['closePrice']
        trading_dates = df_daily['date'].unique()

        # **Sell all current positions**
        total_sell = 0
        for symbol, amount in current_position.items():
            latest_date = df_daily['date'].unique().max()

            if amount > 0: # If we sold more than none
                sell_response = lh.sell(ticker=symbol, amount=amount)

                if 'order_status' in sell_response and sell_response['order_status'] == 'completed': # If successful trade
                    total_sell += amount * sell_response['price']
        
        HAS_POSITION = False

        print(f"Markowitz sold for a value off {total_sell:,.2f} on {latest_date}.")
        current_cash += total_sell
        current_portfolio_value -= total_sell
    
        # Calculate moving average
        df_daily = calculate_moving_average(df_daily, ma_short)
        df_daily = calculate_moving_average(df_daily, ma_long)
        latest_ma = df_daily.sort_values(by='date').groupby('symbol').last()[[f'MA{ma_short}', f'MA{ma_long}']]

        # Calculate market breadth
        market_breadth = (latest_ma[f'MA{ma_short}'] - latest_ma[f'MA{ma_long}'] > 0).sum() / n_assets

        # Only buy if market_breadth > market_breadth_threshold
        if market_breadth > market_breadth_threshold:

            # Calculate log returns
            df_daily['log_return'] = df_daily.groupby('symbol', group_keys=False)['openPrice'].transform(lambda x: np.log(x / x.shift(1)))
            df_daily.dropna(inplace=True)

            # Pivot table to get returns in matrix form (rows = dates, cols = assets)
            df_returns = df_daily.pivot(index='date', columns='symbol', values='log_return')

            if df_returns.empty:
                continue  # Skip if no valid data

            # Select most recent prices and prices ma_short days ago
            current_prices = df_daily[df_daily['date'] == trading_dates[-1]].set_index('symbol')['openPrice']
            past_prices = df_daily[df_daily['date'] == trading_dates[-ma_short]].set_index('symbol')['openPrice']

            # Ensure we have matching assets
            valid_assets = current_prices.index.intersection(past_prices.index)

            # Compute percentage change (mu) from ma_short days ago until now
            mu = (current_prices.loc[valid_assets] / past_prices.loc[valid_assets] - 1).values

            # Compute covariance matrix
            Sigma = df_returns.cov().values  # Covariance matrix

            # Define objective function (negative of return-risk tradeoff)
            def objective(w, mu, Sigma, risk_aversion):
                return - (np.dot(w, mu) - risk_aversion * np.dot(w.T, np.dot(Sigma, w)))

            # Solve the optimization
            result = minimize(objective, w0, args=(mu, Sigma, risk_aversion), 
                            method='SLSQP', bounds=bounds, constraints=constraints)

            # Extract optimal weights
            optimal_weights = result.x

            # Caclulate price budget of stocks
            stocks_price_budget = current_cash * optimal_weights 
            total_buy = 0
            for symbol, price_budget in zip(list(df_returns.columns), stocks_price_budget):
                amount = int(price_budget / latest_prices[symbol])

                if amount > 0: # If we can afford more than none
                    buy_response = lh.buy(ticker=symbol, amount=amount)

                    if 'order_status' in buy_response and buy_response['order_status'] == 'completed': # If successful trade
                        current_position[symbol] = amount
                        total_buy += amount * buy_response['price']
                        HAS_POSITION = True

            print(f"Markowitz bought for a value off {total_buy:,.2f} on {latest_date}.")
            current_cash -= total_buy
            current_portfolio_value += total_buy

            ### END OF BUY REGIME

        # Keep track of portfolio and current balance. 
        print('====================MARKOVITZ CURRENT STATS ====================')
        print(f"Markowitz current liquid capital: ${current_cash:,.2f}")
        print(f"Markowitz current portfolio value: ${current_portfolio_value:,.2f}")
        print(f"Markowitz return since {starting_date} is {(current_cash + current_portfolio_value - starting_capital) / starting_capital:.2f}%") 

        # Wait rebalance_days if currently has a position
        if HAS_POSITION:
            time.sleep(rebalance_days * 8)
        else:
            time.sleep(8) # Wait one days

        # Update df, df_daily
        df_daily = shared.shared_data['df_daily'].copy()

        ### END OF WHILE LOOP
    

        
            