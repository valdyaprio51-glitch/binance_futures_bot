"""
indicators.py
Perhitungan indikator teknikal murni menggunakan Pandas & NumPy:
- Exponential Moving Average (EMA)
- Relative Strength Index (RSI)
- Average True Range (ATR)
- Bollinger Bands (BB)
Tidak membutuhkan library eksternal C seperti TA-Lib, sehingga 100% kompatibel di Windows/Linux/Mac.
"""

import pandas as pd
import numpy as np


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Menghitung Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Menghitung Relative Strength Index (RSI) dengan metode smoothed Wilder.
    """
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's exponential smoothing
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Hindari pembagian nol
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Ganti NaN dengan 50 jika tidak ada pergerakan
    return rsi.fillna(50.0)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Menghitung Average True Range (ATR) untuk mengukur volatilitas pasar.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Menghitung Average Directional Index (ADX) menggunakan metode smoothed Wilder.
    ADX mengukur kekuatan tren pasar (skala 0 - 100):
    - ADX < 20: Pasar sideways / choppy / tidak bertren (hindari entry).
    - ADX >= 20: Tren sehat mulai terbentuk.
    - ADX >= 25: Tren kuat terkonfirmasi (peluang profit momentum tertinggi).
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    pos_dm_s = pd.Series(pos_dm, index=df.index)
    neg_dm_s = pd.Series(neg_dm, index=df.index)

    # Wilder smoothing (alpha = 1.0 / period)
    tr_smooth = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    pos_dm_smooth = pos_dm_s.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    neg_dm_smooth = neg_dm_s.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    pos_di = 100.0 * (pos_dm_smooth / tr_smooth.replace(0, np.nan))
    neg_di = 100.0 * (neg_dm_smooth / tr_smooth.replace(0, np.nan))

    di_diff = (pos_di - neg_di).abs()
    di_sum = pos_di + neg_di
    dx = 100.0 * (di_diff / di_sum.replace(0, np.nan))

    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return adx.fillna(20.0)


def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Menghitung Bollinger Bands: Upper Band, Middle Band (SMA), Lower Band.
    Digunakan untuk mendeteksi kondisi oversold (diskon) dan overbought ekstrem.
    """
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def add_indicators(df: pd.DataFrame, config) -> pd.DataFrame:
    """
    Menambahkan indikator teknikal ke dalam DataFrame klines (OHLCV).
    Kolom input wajib: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    """
    data = df.copy()

    # Pastikan data numerik bertipe float
    for col in ["open", "high", "low", "close", "volume"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    # Hitung Indikator Tren & Momentum
    data["ema_fast"] = calculate_ema(data["close"], getattr(config, "ema_fast_period", 9))
    data["ema_slow"] = calculate_ema(data["close"], getattr(config, "ema_slow_period", 21))
    data["rsi"] = calculate_rsi(data["close"], getattr(config, "rsi_period", 14))
    data["atr"] = calculate_atr(data, 14)

    # Indikator Kekuatan Tren (ADX) & Rata-rata Volume
    data["adx"] = calculate_adx(data, getattr(config, "adx_period", 14))
    vol_period = getattr(config, "volume_sma_period", 20)
    data["volume_sma"] = data["volume"].rolling(window=vol_period).mean().bfill()

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(
        data["close"],
        getattr(config, "bb_period", 20),
        getattr(config, "bb_std_dev", 2.0),
    )
    data["bb_upper"] = bb_upper
    data["bb_middle"] = bb_mid
    data["bb_lower"] = bb_lower

    return data
