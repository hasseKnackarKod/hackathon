# LINC API
import hackathon_linc as lh
lh.init('92438482-5598-4e17-8b34-abe17aa8f598')

# For data handling
import pandas as pd
import numpy as np

# For multi-threading
from threading import Thread
import time

# Miscellaneous
import sys


def main():
    df_historical = pd.DataFrame()
    while True:
        # Create threads
        thread_prints = Thread(target=print_statistics)
        thread_historical_data = Thread(target=load_historical_data, args=(df_historical, 30, None))

        # Start threads
        try: 
            thread_prints.start()
            thread_historical_data.start()
            print(df_historical.head())
        except KeyboardInterrupt:
            print("\nShutdown signal received. Cleaning up...")
            sys.exit()

        # except Exception as error:
        #     print(f"Threads failed with the following error code:\n{error}")
        #     print("")
        #     print("Exiting program...")
        #     sys.exit()


def load_historical_data(df:pd.DataFrame, days_back=30, ticker=None):
    '''Loads historical data for all tickers 30 days back'''
    historical_data = lh.get_historical_data(days_back=30, ticker=None)
    df = pd.DataFrame(historical_data)

    time.sleep(10)


def print_statistics():
    '''Prints the current balance and portfolio every 10 seconds'''
    balance = lh.get_balance()
    print(f"Balance: {balance:.4f}")

    portfolio = lh.get_portfolio()
    for stock, amount in portfolio.items():
        print(f"Stock {stock} has amount {amount}")
        print("")

    time.sleep(10)


if __name__=="__main__":
    main() 
