import pandas as pd
import pandas_ta as ta  # noqa: F401  — registers df.ta accessor


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a DataFrame with columns: open, high, low, close, volume (all lowercase).
    Adds technical indicator columns in-place and returns the augmented df.

    Indicators added:
    - RSI_14: RSI with period 14
    - MACDs_12_26_9: MACD signal line
    - BBP_5_2.0: Bollinger %B (mapped from pandas_ta 'BBP_5_2.0_2.0')
    - SMA20: 20-period simple moving average of close
    - SMA50: 50-period simple moving average of close
    - SMA_cross: +1 if SMA20 > SMA50, -1 if SMA20 < SMA50, 0 if equal
    - ATR_14: Average True Range 14 (mapped from pandas_ta 'ATRr_14')
    - OBV: On-Balance Volume

    NaN values in initial rows (warm-up period) are acceptable.
    """
    # RSI — appends column 'RSI_14'
    df.ta.rsi(length=14, append=True)

    # MACD — appends 'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9'
    df.ta.macd(append=True)

    # Bollinger Bands — appends 'BBP_5_2.0_2.0' (and BBL/BBM/BBU/BBB)
    df.ta.bbands(append=True)
    # Alias to the name used by downstream consumers
    bb_col = next((c for c in df.columns if c.startswith("BBP_")), None)
    if bb_col and "BBP_5_2.0" not in df.columns:
        df["BBP_5_2.0"] = df[bb_col]

    # ATR — appends 'ATRr_14'
    df.ta.atr(length=14, append=True)
    # Alias to the name expected by downstream consumers
    if "ATRr_14" in df.columns and "ATR_14" not in df.columns:
        df["ATR_14"] = df["ATRr_14"]

    # OBV — appends 'OBV'
    df.ta.obv(append=True)

    # Simple moving averages
    df["SMA20"] = df["close"].rolling(window=20).mean()
    df["SMA50"] = df["close"].rolling(window=50).mean()

    # SMA cross: +1 / 0 / -1
    df["SMA_cross"] = 0
    df.loc[df["SMA20"] > df["SMA50"], "SMA_cross"] = 1
    df.loc[df["SMA20"] < df["SMA50"], "SMA_cross"] = -1

    return df
