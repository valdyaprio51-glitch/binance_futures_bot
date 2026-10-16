"""
config.py
Modul konfigurasi untuk Binance Futures Trading Bot.
Membaca environment variables dari file .env dan menyediakan objek Config.
"""

import os
from typing import List
from dataclasses import dataclass
from dotenv import load_dotenv

# Muat file .env jika ada
load_dotenv()


@dataclass
class Config:
    # API credentials
    api_key: str = os.getenv("BINANCE_API_KEY", "")
    api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    use_testnet: bool = os.getenv("USE_TESTNET", "True").strip().lower() in ("true", "1", "yes")

    # Trading Symbols & Timeframe
    timeframe: str = os.getenv("TIMEFRAME", "5m")
    max_active_positions: int = int(os.getenv("MAX_ACTIVE_POSITIONS", "2"))

    @property
    def symbols(self) -> List[str]:
        raw = os.getenv("SYMBOLS", os.getenv("SYMBOL", "SOLUSDT,SUIUSDT,NEARUSDT"))
        return [s.strip().upper() for s in raw.split(",") if s.strip()]

    @property
    def symbol(self) -> str:
        syms = self.symbols
        return syms[0] if syms else "SOLUSDT"

    # Leverage & Margin
    leverage: int = int(os.getenv("LEVERAGE", "3"))
    margin_type: str = os.getenv("MARGIN_TYPE", "ISOLATED").upper()

    # Risk Management
    risk_per_trade_percent: float = float(os.getenv("RISK_PER_TRADE_PERCENT", "8.0"))
    fixed_usdt_per_trade: float = float(os.getenv("FIXED_USDT_PER_TRADE", "0.0"))
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "1.0"))
    take_profit_percent: float = float(os.getenv("TAKE_PROFIT_PERCENT", "2.0"))

    # Auto Break-Even & Tiered Trailing Stop (Kunci Modal & Profit Bertahap)
    enable_break_even: bool = os.getenv("ENABLE_BREAK_EVEN", "True").strip().lower() in ("true", "1", "yes")
    break_even_trigger_percent: float = float(os.getenv("BREAK_EVEN_TRIGGER_PERCENT", "0.6"))

    enable_trailing_stop: bool = os.getenv("ENABLE_TRAILING_STOP", "True").strip().lower() in ("true", "1", "yes")
    # Tier 1: Break-even + fee buffer (Trigger +0.6%, SL ke +0.05%)
    trailing_tier1_profit: float = float(os.getenv("TRAILING_TIER1_PROFIT", "0.6"))
    trailing_tier1_lock: float = float(os.getenv("TRAILING_TIER1_LOCK", "0.05"))
    # Tier 2: Kunci profit separuh (Trigger +1.2%, SL ke +0.6%)
    trailing_tier2_profit: float = float(os.getenv("TRAILING_TIER2_PROFIT", "1.2"))
    trailing_tier2_lock: float = float(os.getenv("TRAILING_TIER2_LOCK", "0.6"))
    # Tier 3: Kunci profit aman (Trigger +1.6%, SL ke +1.0%)
    trailing_tier3_profit: float = float(os.getenv("TRAILING_TIER3_PROFIT", "1.6"))
    trailing_tier3_lock: float = float(os.getenv("TRAILING_TIER3_LOCK", "1.0"))

    # Multi-Timeframe (MTF) Trend Confirmation
    use_mtf_filter: bool = os.getenv("USE_MTF_FILTER", "True").strip().lower() in ("true", "1", "yes")
    mtf_timeframe: str = os.getenv("MTF_TIMEFRAME", "1h")
    mtf_ema_period: int = int(os.getenv("MTF_EMA_PERIOD", "50"))

    # Technical Indicators / Strategy
    ema_fast_period: int = int(os.getenv("EMA_FAST_PERIOD", "9"))
    ema_slow_period: int = int(os.getenv("EMA_SLOW_PERIOD", "21"))
    rsi_period: int = int(os.getenv("RSI_PERIOD", "14"))
    rsi_overbought: float = float(os.getenv("RSI_OVERBOUGHT", "70.0"))
    rsi_oversold: float = float(os.getenv("RSI_OVERSOLD", "30.0"))

    # ADX Trend-Strength & Volume Filter (Anti-Sideways & Anti-Fakeout)
    adx_period: int = int(os.getenv("ADX_PERIOD", "14"))
    adx_threshold: float = float(os.getenv("ADX_THRESHOLD", "20.0"))
    enable_volume_filter: bool = os.getenv("ENABLE_VOLUME_FILTER", "True").strip().lower() in ("true", "1", "yes")
    volume_sma_period: int = int(os.getenv("VOLUME_SMA_PERIOD", "20"))
    volume_factor: float = float(os.getenv("VOLUME_FACTOR", "0.85"))

    # Intraday Seasonality & Global Session Filter
    enable_seasonality_filter: bool = os.getenv("ENABLE_SEASONALITY_FILTER", "True").strip().lower() in ("true", "1", "yes")
    block_dead_zone: bool = os.getenv("BLOCK_DEAD_ZONE", "True").strip().lower() in ("true", "1", "yes")
    avoid_funding_settlement: bool = os.getenv("AVOID_FUNDING_SETTLEMENT", "True").strip().lower() in ("true", "1", "yes")
    asia_adx_minimum: float = float(os.getenv("ASIA_ADX_MINIMUM", "22.0"))

    # Bollinger Bands
    bb_period: int = int(os.getenv("BB_PERIOD", "20"))
    bb_std_dev: float = float(os.getenv("BB_STD_DEV", "2.0"))

    # Polling Interval
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

    def validate(self):
        """Memvalidasi konfigurasi penting sebelum bot berjalan."""
        errors = []
        if not self.api_key or self.api_key == "masukkan_api_key_anda_di_sini":
            errors.append("BINANCE_API_KEY belum diisi di file .env!")
        if not self.api_secret or self.api_secret == "masukkan_api_secret_anda_di_sini":
            errors.append("BINANCE_API_SECRET belum diisi di file .env!")
        if self.leverage < 1 or self.leverage > 125:
            errors.append(f"LEVERAGE tidak valid ({self.leverage}). Harus antara 1 - 125.")
        if self.margin_type not in ("ISOLATED", "CROSSED"):
            errors.append(f"MARGIN_TYPE ({self.margin_type}) tidak valid. Gunakan ISOLATED atau CROSSED.")
        if self.stop_loss_percent <= 0:
            errors.append("STOP_LOSS_PERCENT harus lebih besar dari 0.")
        if self.take_profit_percent <= 0:
            errors.append("TAKE_PROFIT_PERCENT harus lebih besar dari 0.")
        if not self.symbols:
            errors.append("Tidak ada simbol trading yang dikonfigurasi di SYMBOLS atau SYMBOL!")
        if self.max_active_positions < 1:
            errors.append(f"MAX_ACTIVE_POSITIONS tidak valid ({self.max_active_positions}). Minimal 1.")

        if errors:
            raise ValueError("\n".join(errors))


# Inisialisasi konfigurasi default
config = Config()

