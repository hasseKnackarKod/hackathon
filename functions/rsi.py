import pandas as pd

def calculate_hourly_rsi(df: pd.DataFrame, period=14) -> pd.DataFrame:
    """
    Calculates the hourly Relative Strength Index (RSI) for a given dataframe.
    
    Parameters:
        df (pd.DataFrame): Input dataframe with columns ['gmtTime', 'symbol', 'price'].
        period (int): Lookback period for RSI calculation (default: 14).
    
    Returns:
        pd.DataFrame: Original dataframe with an additional 'RSI' column.
    """
    df = df.copy()  # Avoid modifying original dataframe
    
    # Ensure data is sorted
    df = df.sort_values(by=['symbol', 'gmtTime'])
    
    # Compute price change
    df['price_diff'] = df.groupby('symbol')['price'].diff()

    # Compute gains and losses
    df['gain'] = df['price_diff'].apply(lambda x: x if x > 0 else 0)
    df['loss'] = df['price_diff'].apply(lambda x: -x if x < 0 else 0)

    # Compute rolling average of gains and losses
    df['avg_gain'] = df.groupby('symbol')['gain'].transform(lambda x: x.rolling(window=period, min_periods=1).mean())
    df['avg_loss'] = df.groupby('symbol')['loss'].transform(lambda x: x.rolling(window=period, min_periods=1).mean())

    # Compute RSI
    df['RS'] = df['avg_gain'] / df['avg_loss']
    df['RSI'] = 100 - (100 / (1 + df['RS']))

    # Handle cases where loss is zero (avoid division by zero)
    df['RSI'] = df['RSI'].fillna(100)  # If no losses, RSI = 100

    # Drop intermediate columns
    df = df.drop(columns=['price_diff', 'gain', 'loss', 'avg_gain', 'avg_loss', 'RS'])

    return df

import pandas as pd

def calculate_daily_rsi(df: pd.DataFrame, period=14) -> pd.DataFrame:
    """
    Calculates the daily Relative Strength Index (RSI) for a given dataframe.
    Only considers data between 07:00 and 15:00 before aggregating to daily prices.

    Parameters:
        df (pd.DataFrame): Input dataframe with columns ['gmtTime', 'symbol', 'price'].
        period (int): Lookback period for RSI calculation (default: 14).

    Returns:
        pd.DataFrame: Dataframe with daily RSI values.
    """
    df = df.copy()  # Avoid modifying the original dataframe
    df['date'] = df['gmtTime'].dt.date  # Extract date only (ignores time)

    # Aggregate daily open and close prices
    df_daily = df.groupby(['symbol', 'date']).agg(
        open_price=('price', 'first'),  # First price of the day (07:00)
        close_price=('price', 'last')   # Last price of the day (15:00)
    ).reset_index()

    # Sort values
    df_daily = df_daily.sort_values(by=['symbol', 'date'])

    # Compute price change using close prices
    df_daily['price_diff'] = df_daily.groupby('symbol')['close_price'].diff()

    # Compute gains and losses
    df_daily['gain'] = df_daily['price_diff'].apply(lambda x: x if x > 0 else 0)
    df_daily['loss'] = df_daily['price_diff'].apply(lambda x: -x if x < 0 else 0)

    # Compute rolling average of gains and losses
    df_daily['avg_gain'] = df_daily.groupby('symbol')['gain'].transform(lambda x: x.rolling(window=period, min_periods=1).mean())
    df_daily['avg_loss'] = df_daily.groupby('symbol')['loss'].transform(lambda x: x.rolling(window=period, min_periods=1).mean())

    # Compute RSI
    df_daily['RS'] = df_daily['avg_gain'] / df_daily['avg_loss']
    df_daily['RSI'] = 100 - (100 / (1 + df_daily['RS']))

    # Handle cases where loss is zero (avoid division by zero)
    df_daily['RSI'] = df_daily['RSI'].fillna(100)  # If no losses, RSI = 100

    # Drop intermediate columns
    df_daily = df_daily.drop(columns=['price_diff', 'gain', 'loss', 'avg_gain', 'avg_loss', 'RS'])

    return df_daily

