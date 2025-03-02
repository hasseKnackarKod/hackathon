# LINC API
import hackathon_linc as lh

# For data handling
import pandas as pd
import numpy as np
from datetime import timedelta

# For multi-threading
from threading import Thread, Event
import time
from multiprocessing import freeze_support
shutdown_event = Event()

# For shared data
import shared
from functions.metrics import calculate_rsi

# Import strategies
from markowitz import markowitz
from diverundmom import DivergenceModel
from rsiindex import opportunistic_rsi

# For logging
from logger import setup_logger
logger = setup_logger('main', 'logs/main.log')


# Not used
def append_new_data(df: pd.DataFrame, df_daily: pd.DataFrame, days_back=5, ticker=None):
    '''Loads historical data for all tickers some days back. Increase days_back if the API is very slow with updates.'''

    # Fetch new data from API
    df_new_data = pd.DataFrame(lh.get_historical_data(days_back=days_back, ticker=ticker))

    if df_new_data is None or df_new_data.empty:
        logger.warning("No new data available from API.")
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

    # Store in shared_data
    shared.shared_data['df'] = df
    logger.info("New data appended successfully.")

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

        # Store in shared_data
        shared.shared_data['df_daily'] = df_daily

    return

def initialize_dataframes():   
    # Try to get historical data
    try: 
        df = pd.DataFrame(lh.get_historical_data(days_back=252, ticker=None))
        if df is None or df.empty:
            logger.critical("Historical data is empty.")
            raise ValueError("No historical data available")
    except ConnectionError as e:
        logger.critical(f"Failed to fetch historical data: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error in initialize_dataframes: {e}")
        raise

    # Add date column and convert date columns to datetime
    df['gmtTime'] = pd.to_datetime(df['gmtTime'])
    df['date'] = pd.to_datetime(df['gmtTime'].dt.date)

    # Add price column
    df['price'] = (df['askMedian'] + df['bidMedian']) / 2

    # Sort values
    df = df.sort_values(by='gmtTime')

    # Aggregate daily open and close prices (assumes historical data contains full days)
    df_daily = df.groupby(['symbol', 'date']).agg(
        openPrice=('price', 'first'),  # First price of the day
        closePrice=('price', 'last'),  # Last price of the day
        askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
        bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
    ).reset_index()

    # Sort values
    df_daily = df_daily.sort_values(by='date')

    # Store in shared_data
    shared.shared_data['df'] = df
    shared.shared_data['df_daily'] = df_daily
    return

def main():
    try:
        lh.init('87bb5e63-7539-427f-b65e-66f1e6b6f016')
    except ConnectionError as e:
        logger.critical(f"API connection failed: {e}")
        return
    except Exception as e:
        logger.critical(f"Unexpected error during API init: {e}")
        return

    # Strategy allocations
    starting_allocs = [0.15, 0.80, 0.50, 0.05] # Index, markowitz, diverundmom, liquid
    starting_balance = lh.get_balance()

    # Initialize data
    try:
        initialize_dataframes()
    except ValueError:
        logger.critical("Initial data is empty or none! Shutting down...")
        return
    except ConnectionRefusedError:
        logger.critical("Failed to gather initial data! Shutting down...")
        return

    logger.info("Starting trading strategies...")

    # RSI index strategy
    rsi_thread = Thread(target=opportunistic_rsi, args=(starting_balance * starting_allocs[0], ), daemon=True)

    # Markowitz strategy
    markowitz_thread = Thread(target=markowitz, args=(starting_balance * starting_allocs[1], ), daemon=True)

    # Diverence and momentum strategy
    divergence_thread = Thread(target=DivergenceModel(starting_balance * starting_allocs[2]).run, daemon=True)

    # Start threads
    markowitz_thread.start()
    divergence_thread.start()
    rsi_thread.start()

    try:         
        while not shutdown_event.is_set():
            # Update data
            try: 
                df = pd.DataFrame(lh.get_historical_data(days_back=252, ticker=None))
                if df is None or df.empty:
                    logger.warning("No new data! Waiting for new data...")
                    time.sleep(1)
                    continue
            except:
                logger.warning("Failed to connect to API in loop! Waiting for connection...")
                time.sleep(1)
                continue

            # Add date column and convert date columns to datetime
            df['gmtTime'] = pd.to_datetime(df['gmtTime'])
            df['date'] = pd.to_datetime(df['gmtTime'].dt.date)

            # Add price column
            df['price'] = (df['askMedian'] + df['bidMedian']) / 2

            # Sort values
            df = df.sort_values(by='gmtTime')

            # Aggregate daily open and close prices (assumes historical data contains full days)
            df_daily = df.groupby(['symbol', 'date']).agg(
                openPrice=('price', 'first'),  # First price of the day
                closePrice=('price', 'last'),  # Last price of the day
                askVolume=('askVolume', 'sum'), # Sum ask volume over the entire day
                bidVolume=('bidVolume', 'sum') # Sum bid volume over the entire day
            ).reset_index()

            # Sort values
            df_daily = df_daily.sort_values(by='date')

            # Store in shared_data
            shared.shared_data['df'] = df
            shared.shared_data['df_daily'] = df_daily

            logger.info(f"Latest market data update received: {df['gmtTime'].max()} for {len(df)} records.")
            
            time.sleep(1)

    except KeyboardInterrupt:
        # Stop all threads
        logger.info("Shutdown signal received. Stopping all strategies...")
        shutdown_event.set()
        markowitz_thread.join()
        rsi_thread.join()
        divergence_thread.join()
        logger.info("All strategy threads stopped.")

        # Sell remaining stocks with infinite retry
        logger.info("Selling all non-index stocks before exit...")

        while True:
            try:
                portfolio = lh.get_portfolio()  # Try to fetch the latest portfolio
                for symbol, amount in portfolio.items():
                    if amount > 0 and symbol != 'INDEX1':
                        logger.info(f"Attempting to sell {amount} of {symbol}...")
                        lh.sell(symbol, amount)
                break  # If it reaches this point, all sells succeeded
            except Exception as e:
                logger.warning(f"Failed to complete sell orders: {e}. Retrying in 5 seconds...")
                time.sleep(5)  # Wait before retrying

        logger.info("Sells completed successfully!")
        logger.info(f"Final portfolio state: {portfolio}")

        return  # Exits 'main()' gracefully


if __name__ == "__main__":
    freeze_support()  # Required for Windows multiprocessing

    logger.info("Starting program...")

    # Initialize shared data inside main
    shared.shared_data = shared.get_shared_data()  

    main()
