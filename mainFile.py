# LINC API
import hackathon_linc as lh

# For data handling
import pandas as pd
import numpy as np
from datetime import timedelta

# For multi-threading
from threading import Thread, Lock
import time
df_lock = Lock()
from multiprocessing import freeze_support

# For shared data
import shared

# Import strategies
from markowitz import markowitz
from diverundmom import LiveTradingModel

# Miscellaneous
import sys

def initialize_dataframes():   
    # Read historical data
    df = pd.read_csv('historical_data/stockPrices_hourly.csv')

    # Add date column and convert date columns to datetime
    df['gmtTime'] = pd.to_datetime(df['gmtTime'])
    df['date'] = pd.to_datetime(df['gmtTime'].dt.date)

    # Add price column
    df['price'] = (df['askMedian'] + df['bidMedian']) / 2

    # Sort values
    df = df.sort_values(by=['symbol', 'gmtTime'])

    # **Maintain rolling window**
    max_rows = np.inf
    if len(df) > max_rows:
        df = df.iloc[-max_rows:]  # Keep only last max_rows entries

    # Aggregate daily open and close prices (assumes historical data contains full days)
    df_daily = df.groupby(['symbol', 'date']).agg(
        openPrice=('price', 'first'),  # First price of the day
        closePrice=('price', 'last'),  # Last price of the day
        askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
        bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
    ).reset_index()

    # Sort values
    df_daily = df_daily.sort_values(by=['symbol', 'date'])

    # Store in shared_data
    shared.shared_data['df'] = df
    shared.shared_data['df_daily'] = df_daily

def append_new_data(df: pd.DataFrame, df_daily: pd.DataFrame, days_back=5, ticker=None):
    '''Loads historical data for all tickers some days back. Increase days_back if the API is very slow with updates.'''

    # Fetch new data from API
    df_new_data = pd.DataFrame(lh.get_historical_data(days_back=days_back, ticker=ticker))

    if df_new_data is None or df_new_data.empty:
        print("No new data")
        return df, df_daily # No change

    # Add date column and convert date columns to datetime
    df_new_data['gmtTime'] = pd.to_datetime(df_new_data['gmtTime'])
    df_new_data['date'] = pd.to_datetime(df_new_data['gmtTime'].dt.date)

    # Add price column
    df_new_data['price'] = (df_new_data['askMedian'] + df_new_data['bidMedian']) / 2

    # **Filter new data only (avoid full concat)**
    latest_time = df['gmtTime'].max() if not df.empty else None
    if latest_time:
        df_new_data = df_new_data[df_new_data['gmtTime'] > latest_time]

    if df_new_data.empty:
        return df, df_daily # No change

    # **Append new data**
    df = pd.concat([df, df_new_data], ignore_index=True).reset_index(drop=True)

    # **Maintain rolling window**
    max_rows = 10000
    if len(df) > max_rows:
        df = df.iloc[-max_rows:]  # Keep only last max_rows entries

    # Sort values
    df = df.sort_values(by=['symbol', 'gmtTime'])

    # **Update df_daily using only new and full days**
    last_daily_date = df_daily['date'].max() # Last date of df_daily
    last_date = df['date'].max() # Last date of df

    # Get all full days not already in df_daily
    df_new_full_days = df_new_data[(df_new_data['date'] > last_daily_date) & (df_new_data['date'] < last_date)]

    if not df_new_full_days.empty:
        # **Aggregate daily open & close prices**
        df_daily_new = df_new_full_days.groupby(['symbol', 'date']).agg(
                openPrice=('price', 'first'), # First recorded price within valid hours
                closePrice=('price', 'last'), # Last recorded price within valid hours
                askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
                bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
            ).reset_index()
        
        # **Append to df_daily**
        df_daily = pd.concat([df_daily, df_daily_new]).reset_index(drop=True)

        # Sort values
        df_daily = df_daily.sort_values(by=['symbol', 'date'])
 
    return [df, df_daily]


def main():
    lh.init('92438482-5598-4e17-8b34-abe17aa8f598')

    # Strategy allocations
    starting_allocs = [0.25, 0.5, 0.2, 0.05]
    starting_balance = lh.get_balance()

    # Initialize data
    initialize_dataframes()

    # Start background threads
    update_thread = Thread(target=update_df, daemon=True)
    stats_thread = Thread(target=print_stats, args=(starting_balance, ), daemon=True)

    # *Start Live Trading Model in a Thread*
    # diverundmom = LiveTradingModel(starting_balance * starting_allocs[1])  # Allocate 50% of funds
    # diverundmom_thread = Thread(target=diverundmom.run, daemon=True)  # Daemon threa

    markowitz_thread = Thread(target=markowitz, args=(starting_balance * starting_allocs[0], ), daemon=True)

    update_thread.start()
    stats_thread.start()

    markowitz_thread.start()
    # diverundmom_thread.start()

    try: 
        # Keep main thread alive
        while True:
            time.sleep(10)

    except KeyboardInterrupt:
        print("\nShutdown signal received. Selling all stocks and turning off...")

        current_portfolio = lh.get_portfolio()

            # Loop through portfolio and sell evertyhing
        for symbol, amount in current_portfolio.items():
            if amount > 0:
                lh.sell(symbol, amount)
        
        print("Sells completed!")
        print(f"Final portfolio: {lh.get_portfolio()}")

        return  # Exits 'main()' gracefully


def update_df():
    """Thread-safe function to update df in the main loop."""    
    while True:
        with df_lock:  # Ensure thread safety
            df, df_daily = append_new_data(
                shared.shared_data['df'], shared.shared_data['df_daily'], days_back=3, ticker=None
            )
            shared.shared_data['df'], shared.shared_data['df_daily'] = df, df_daily

        time.sleep(1)  # Control update frequency


def print_stats(starting_balance: float):    
    current_balance = lh.get_balance()
    current_portfolio = lh.get_portfolio()

    df = shared.shared_data['df']  # Safely get latest df

    stock_portfolio_value = 0
   
    # Get the latest price for each stock
    df_last_prices = df.sort_values(by='gmtTime').groupby('symbol').last()['price']

    # Loop through and save stock specific data
    for symbol, amount in current_portfolio.items():
        last_price = df_last_prices[symbol]
        # print(f"-----{symbol}-----\nAmount: {amount}, Price: {last_price:.2f}, Value: {amount * last_price:.2f}")
        stock_portfolio_value += amount * last_price

    print("-----STATS------")
    print(f"Portfolio: {current_portfolio}")
    print(f"Current balance: {current_balance:.2f}")
    print(f"Stock portfolio value: {stock_portfolio_value:.2f}", )
    print(f"Total value: {stock_portfolio_value + current_balance:.2f}")
    print(f"Percentage change since start: {100* (stock_portfolio_value + current_balance - starting_balance) / starting_balance:.2}%")

    time.sleep(60) # Control update frequency


if __name__ == "__main__":
    freeze_support()  # Required for Windows multiprocessing

    # Now initialize shared data inside main
    shared.shared_data = shared.get_shared_data()  

    main()
