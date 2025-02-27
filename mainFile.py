# LINC API
import hackathon_linc as lh
lh.init('92438482-5598-4e17-8b34-abe17aa8f598')

# For data handling
import pandas as pd
import numpy as np
from datetime import timedelta

# For multi-threading
from threading import Thread
import time

# Miscellaneous
import sys

# Global variables
DF = pd.DataFrame()
DF_DAILY = pd.DataFrame()

def initialize_dataframes():
    global DF, DF_DAILY
    
    # Read historical data
    DF = pd.read_csv('historical_data/stockPrices_hourly.csv')

    # Convert date column to datetime objects
    DF['gmtTime'] = pd.to_datetime(DF['gmtTime'])

    # Add price column
    DF['price'] = (DF['askMedian'] + DF['bidMedian']) / 2

    # Add pure date column
    DF['date'] = DF['gmtTime'].dt.date
    DF['date'] = pd.to_datetime(DF['date'])  # Convert to datetime

    # Sort values
    DF = DF.sort_values(by=['symbol', 'gmtTime'])

    # Aggregate daily open and close prices
    DF_DAILY = DF.groupby(['symbol', 'date']).agg(
        openPrice=('price', 'first'),  # First price of the day (07:00)
        closePrice=('price', 'last'),  # Last price of the day (15:00)
        askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
        bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
    ).reset_index()

    # Sort values
    DF_DAILY = DF_DAILY.sort_values(by=['symbol', 'date'])

def append_new_data(DF: pd.DataFrame, DF_DAILY: pd.DataFrame(), days_back=5, ticker=None):
    '''Loads historical data for all tickers some days back. Increase days_back if the API is very slow with updates.'''

    # Fetch new data from API
    df_new_data = pd.DataFrame(lh.get_historical_data(days_back=days_back, ticker=ticker))

    # If no new data, return original dataframe
    if df_new_data.empty:
        print("No new data")
        return DF

    # Convert date column to datetime objects
    df_new_data['gmtTime'] = pd.to_datetime(df_new_data['gmtTime'])

    # Add pure date column
    df_new_data['date'] = df_new_data['gmtTime'].dt.date
    df_new_data['date'] =  pd.to_datetime(df_new_data['date'])

    # Add price column
    df_new_data['price'] = (df_new_data['askMedian'] + df_new_data['bidMedian']) / 2

    # Append new data to dataframe and remove duplicate rows
    # DF = df_new_data.merge(right=DF, on=['gmtTime', 'symbol'], how='outer').drop_duplicates(subset=['gmtTime', 'symbol'], keep='last')
    DF = pd.concat([DF, df_new_data]).drop_duplicates(subset=['gmtTime', 'symbol'], keep='last').reset_index(drop=True)

    # Sort values
    DF = DF.sort_values(by=['symbol', 'gmtTime'])

    # If DF is at least 2 days ahead of DF_DAILY, update it
    if (DF['date'].max()-DF_DAILY['date'].max()).days >= 2:
        # Keep track of first and last date
        min_date = DF_DAILY['date'].min()
        max_date = DF_DAILY['date'].max()

        # Aggregate daily open and close prices
        df_daily_new = df_new_data[(df_new_data['date'] != min_date) & (df_new_data['date'] != max_date)].groupby(['symbol', 'date']).agg(
            openPrice=('price', 'first'),  # First price of the day (07:00)
            closePrice=('price', 'last'),  # Last price of the day (15:00)
            askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
            bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
        ).reset_index()

        DF_DAILY = pd.concat([DF_DAILY, df_daily_new]).drop_duplicates(subset=['date', 'symbol'], keep='last').reset_index(drop=True)

        # Sort values
        DF_DAILY = DF_DAILY.sort_values(by=['symbol', 'date'])
 
    return [DF, DF_DAILY]


def main():

    # Attributes
    global DF, DF_DAILY

    # Strategy allocations
    starting_allocs = [0.25, 0.5, 0.2, 0.05]
    starting_balance = lh.get_balance()

    # Initialize data
    initialize_dataframes()

    # Infinite loop
    while True:

        # Create threads
        try:
            append_data_thread = Thread(target=lambda: update_df())
            append_data_thread.start()

            print_stats_thread = Thread(target=lambda: print_stats(starting_balance))
            print_stats_thread.start()

            # Add one thread per strategy, with the starting balance as argument and handled by the strategy
            # thread1 = Thread(target=function, args=(starting_balance * starting_allocs[0]))

        except KeyboardInterrupt:
            print("\nShutdown signal received. Selling all stocks and turning off...")

            current_portfolio = lh.get_portfolio()

             # Loop through portfolio and sell evertyhing
            for symbol, amount in current_portfolio.items():
                if amount > 0:
                    lh.sell(symbol, amount)
            
            print("Sells completed!")
            print(f"Final portfolio: {lh.get_portfolio()}")

            sys.exit()



def update_df():
    """Thread-safe function to update DF in the main loop."""
    global DF, DF_DAILY  # Ensure we're modifying the correct DF
    DF, DF_DAILY = append_new_data(DF, DF_DAILY, days_back=3, ticker=None)
    time.sleep(1)


def print_stats(starting_balance: float):
    # Portfolio balance
    current_balance = lh.get_balance()
    
    # Initialize portoflio values
    current_portfolio = lh.get_portfolio()
    print(f"Portfolio: {current_portfolio}")
    stock_portfolio_value = 0
   
    # Get the latest price for each stock
    df_last_prices = DF.sort_values(by='gmtTime').groupby('symbol').last().reset_index()[['symbol', 'price']]

    # Loop through and save stock specific data
    for symbol, amount in current_portfolio.items():
        last_price = df_last_prices[df_last_prices['symbol'] == symbol]['price'].values[0]
        # print(f"-----{symbol}-----\nAmount: {amount}, Price: {last_price:.2f}, Value: {amount * last_price:.2f}")
        stock_portfolio_value += amount * last_price

    print(f"Current balance: {current_balance:.2f}")
    print(f"Stock portfolio value: {stock_portfolio_value:.2f}", )
    print(f"Total value: {stock_portfolio_value + current_balance:.2f}")

    print(f"Percentage change since start: {100* (stock_portfolio_value + current_balance - starting_balance) / starting_balance:.6}%")

    time.sleep(60)


if __name__=="__main__":
    main() 
