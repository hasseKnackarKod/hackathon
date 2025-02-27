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
    current_position = {symbol: 0 for symbol in symbols}
    current_capital = starting_capital
    current_portfolio_value = 0
    starting_date = df_daily['date'].unique().max()
    
    while True:
        latest_prices = df_daily.sort_values(by='date').groupby('symbol').last()['closePrice']

        # **Sell all current positions**
        for symbol, amount in current_position.items():
            total_sell = 0
            latest_date = df_daily['date'].max()
            if amount > 0:
                lh.sell(ticker=symbol, amount=amount)
                total_sell += amount * latest_prices[symbol]

        print(f"Markowitz sold for a value off {total_sell:.2f} on {latest_date}.")
        current_capital += total_sell
        current_portfolio_value -= total_sell

        # **Maintain rolling window**
        max_days = 252
        if len(df_daily['date'].unique()) > max_days:
            df_daily = df_daily.iloc[-max_days:]

        # Calculate log returns
        df_daily['log_return'] = df_daily.groupby('symbol', group_keys=False)['openPrice'].transform(lambda x: np.log(x / x.shift(1)))
        df_daily.dropna(inplace=True)

        # Pivot table to get returns in matrix form (rows = dates, cols = assets)
        df_returns = df_daily.pivot(index='date', columns='symbol', values='log_return')

        # Compute mean returns and covariance matrix
        mu = df_returns.mean().values  # Expected returns (mean of each column)
        Sigma = df_returns.cov().values  # Covariance matrix

        # Risk aversion parameter (adjust as needed)
        lambda_ = 0.5  # Higher value means more risk aversion

        # Number of assets
        n_assets = len(mu)

        # Initial guess: Equal weights
        w0 = np.ones(n_assets) / n_assets  

        # Constraints: Sum of weights = 1
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})

        # Bounds: Ensure weights are non-negative (no short selling)
        bounds = [(0, 1)] * n_assets

        # Define the objective function to minimize (negative of our function)
        def objective(w, mu, Sigma, lambda_):
            return - (np.dot(w, mu) - lambda_ * np.dot(w.T, np.dot(Sigma, w)))

        # Solve the optimization
        result = minimize(objective, w0, args=(mu, Sigma, lambda_), 
                        method='SLSQP', bounds=bounds, constraints=constraints)

        # Extract optimal weights
        optimal_weights = result.x

        # Caclulate number of stocks to buy (rounded down)
        stocks_amount = current_capital * optimal_weights / sum(optimal_weights)
        stocks_amount = [int(amount) for amount in stocks_amount]

        for symbol, amount in zip(list(df_returns.columns), stocks_amount):
            total_buy = 0
            if amount > 0:
                current_position[symbol] = amount
                lh.buy(ticker=symbol, amount=amount)
                total_buy += amount * latest_prices[symbol]

        print(f"Markowitz bought for a value off {total_buy:.2f} on {latest_date}.")
        current_capital -= total_buy
        current_portfolio_value += total_buy

        # Keep track of portfolio and current balance. 
        print(f"Current Markowitz liquid capital: ${current_capital:.2f}")
        print(f"Current Markowitz portfolio value: ${current_portfolio_value}")
        print(f"Markowitz return since {starting_date} is {(current_capital + current_portfolio_value - starting_capital) / starting_capital:.2f}%") 
        
        # Update df, df_daily
        df_daily = shared.shared_data['df_daily'].copy()

        time.sleep(30*8) # Jajemän gubbs, såhär väntar jag på att 30 dagar passerat. Peak performance!
    

        
            