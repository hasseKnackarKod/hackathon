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

def initialize_dataframes():   
    # Read historical data
    historical_data = lh.get_historical_data(days_back=252, ticker=None)
    df = pd.DataFrame(data=historical_data)
    # df = pd.read_csv('historical_data/stockPrices_hourly.csv')

    # Add date column and convert date columns to datetime
    df['gmtTime'] = pd.to_datetime(df['gmtTime'])
    df['date'] = pd.to_datetime(df['gmtTime'].dt.date)

    # Add price column
    df['price'] = (df['askMedian'] + df['bidMedian']) / 2

    # Sort values
    df = df.sort_values(by='gmtTime')

    # **Maintain rolling window**
    max_rows = 8*252
    max_rows *= len(df['symbol'].unique())
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
    df_daily = df_daily.sort_values(by='date')

    # **Maintain rolling window**
    max_rows = 252
    max_rows *= len(df_daily['symbol'].unique())
    if len(df_daily) > max_rows:
        df_daily = df_daily.iloc[-max_rows:]  # Keep only last max_rows entries

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

    # Sort values
    df = df.sort_values(by='gmtTime')

    # **Maintain rolling window**
    max_rows = 8*252
    max_rows *= len(df['symbol'].unique())
    if len(df) > max_rows:
        df = df.iloc[-max_rows:]  # Keep only last max_rows entries

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
        df_daily = df_daily.sort_values(by='date')

        # **Maintain rolling window**
        max_rows = 252
        max_rows *= len(df_daily['symbol'].unique())
        if len(df_daily) > max_rows:
            df_daily = df_daily.iloc[-max_rows:]  # Keep only last max_rows entries
 
    return [df, df_daily]


def main():
    lh.init('87bb5e63-7539-427f-b65e-66f1e6b6f016')

    # Strategy allocations
    starting_allocs = [0.15, 0.2, 0.6, 0.05] # Index, markowitz, diverundmom, liquid
    starting_balance = lh.get_balance()

    # Initialize data
    initialize_dataframes()

    # Background threads
    update_thread = Thread(target=update_df, daemon=True)
    stats_thread = Thread(target=print_stats, args=(starting_balance, ), daemon=True)

    # Markowitz strategy
    markowitz_thread = Thread(target=markowitz, args=(starting_balance * starting_allocs[1], ), daemon=True)

    # Diverence and momentum strategy
    diverundmom = LiveTradingModel(starting_balance * starting_allocs[2])  # Allocate 50% of funds
    diverundmom_thread = Thread(target=diverundmom.run, daemon=True)  # Daemon threa

    # Start threads
    update_thread.start()
    stats_thread.start()

    markowitz_thread.start()
    diverundmom_thread.start()

    try: 
        # Buy index for every month for some months
        nbr_index_buying_months = 5
        for i in range(nbr_index_buying_months):
            latest_prices = shared.shared_data['df_daily'].sort_values(by='date').groupby('symbol').last()['closePrice']
            amount = int( (starting_balance * starting_allocs[0] / latest_prices['INDEX1'] ) / nbr_index_buying_months) 
            buy_response = lh.buy(ticker='INDEX1', amount=amount)

            if buy_response['order_status'] == 'completed':
                print(f"Bought index for ${amount * buy_response['price']:,.2f}!")
            else:
                print(f"Failed to buy index. Order status: {buy_response['order_status']}")

            time.sleep(8*21) # Wait one month
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
