import pandas as pd
import hackathon_linc as lh
import shared
from functions.metrics import calculate_rsi
import time
from logger import setup_logger
logger = setup_logger('index', 'logs/index.log')

def opportunistic_rsi(starting_capital: float):
    logger.info("Starting Opportunistic RSI strategy...")

    data_empty = True
    while data_empty:
        df_daily = pd.DataFrame(shared.shared_data.get('df_daily', pd.DataFrame()).copy())
        if df_daily.empty:
            logger.error("Initial df_daily is empty! Waiting for data...")
            data_empty = True
        else:
            data_empty = False
    
    nbr_index_buys = 2

    while True:
        if data_empty:
            logger.error("df_daily is empty! Waiting for data...")
            time.sleep(8) # Wait a day
            continue
        try:
            df_rsi = calculate_rsi(df_daily, 21)
            index_rsi = df_rsi[(df_rsi['symbol'] == 'INDEX1') & (df_rsi['date'] == df_rsi['date'].max())]

            if not index_rsi.empty and index_rsi['RSI21'].values[0] < 25:
                latest_prices = df_daily.sort_values(by='date').groupby('symbol').last()['closePrice']
                amount = int((starting_capital / latest_prices['INDEX1']) / nbr_index_buys)

                try:
                    buy_response = lh.buy(ticker='INDEX1', amount=amount)
                    if buy_response and buy_response.get('order_status') == 'completed':
                        logger.info(f"Bought INDEX1 for ${amount * buy_response['price']:,.2f}!")
                    else:
                        logger.warning(f"Failed to buy INDEX1. Order status: {buy_response.get('order_status', 'unknown')}")
                except Exception as e:
                    logger.error(f"Error while placing buy order: {e}")

            time.sleep(8) # Wait a day

            # Update df_daily
            df_daily = shared.shared_data.get('df_daily', pd.DataFrame()).copy()
            data_empty = df_daily.empty

        except Exception as e:
            logger.error(f"Unexpected error in opportunistic_rsi loop: {e}")
            time.sleep(8)  # Wait a day

