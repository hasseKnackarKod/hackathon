import pandas as pd

def calculate_rsi(df: pd.DataFrame, period=14) -> pd.DataFrame:
    """
    Calculates the hourly Relative Strength Index (RSI) for a given dataframe and period.
    
    Parameters:
        df (pd.DataFrame): Input dataframe with sorted symbol and price columns.
        period (int): Lookback period for RSI calculation (default: 14).
    
    Returns:
        pd.DataFrame: Original dataframe with an additional 'RSI' column.
    """
    df = df.copy()  # Avoid modifying original dataframe

    # Detect price or open_price
    price_column = 'open_price' if 'open_price' in df.columns else 'price'

    # Compute price change
    df['price_diff'] = df.groupby('symbol')[price_column].diff()

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