import pandas as pd

def calculate_moving_average(df: pd.DataFrame, period=14) -> pd.DataFrame:
    """
    Calculates the hourly moving average (MA) for a given dataframe and period.
    
    Parameters:
        df (pd.DataFrame): Input dataframe with sorted symbol and price columns.
        period (int): Rolling window period for MA calculation (default: 14).
    
    Returns:
        pd.DataFrame: Original dataframe with an additional 'Hourly_MA_{period}' column.
    """
    df = df.copy() # Avoid modifying original dataframe
       
    # Detect price or open_price
    price_column = 'open_price' if 'open_price' in df.columns else 'price'

    # Compute rolling mean using transform to maintain index alignment
    df[f'MA_{period}'] = df.groupby('symbol')[price_column].transform(lambda x: x.rolling(window=period, min_periods=1).mean())

    return df