"""
strategy.py
Logika strategi trading kuantitatif profesional untuk Binance Futures:
1. Multi-Timeframe Alignment (MTF): Filter tren makro 1 Jam (EMA 50) agar selalu trading searah tren besar.
2. Bollinger Bands + RSI Pullback: Deteksi titik jenuh/diskon (oversold di support BB) untuk entry probabilitas tinggi.
3. EMA Crossover (9/21): Konfirmasi momentum pembalikan arah jangka pendek pada candle 5 menit.
"""

from typing import Dict, Any, Optional
import pandas as pd
from indicators import calculate_ema


class EmaRsiStrategy:
    """
    Strategi Pro High-Probability Trend & Pullback:
    - Sinyal BUY (LONG):
        1. Tren Makro 1 Jam harus BULLISH (Harga 1H > EMA 50 1H).
        2. Candle 5m mengalami pullback/diskon di dekat pita bawah Bollinger Bands (atau Golden Cross 9/21).
        3. RSI berada di zona sehat / pantulan naik (RSI 40 - 70).
    - Sinyal SELL (SHORT):
        1. Tren Makro 1 Jam harus BEARISH (Harga 1H < EMA 50 1H).
        2. Candle 5m mengalami overbought di dekat pita atas Bollinger Bands (atau Death Cross 9/21).
        3. RSI berada di zona sehat / pantulan turun (RSI 30 - 60).
    """

    def __init__(self, config):
        self.config = config

    def evaluate_macro_trend(self, df_mtf: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Mengevaluasi arah tren makro pada timeframe lebih tinggi (misal 1 Jam)."""
        if df_mtf is None or len(df_mtf) < getattr(self.config, "mtf_ema_period", 50) + 2:
            return {"status": "NEUTRAL", "reason": "Data MTF belum cukup"}

        closes = pd.to_numeric(df_mtf["close"], errors="coerce")
        ema_mtf = calculate_ema(closes, getattr(self.config, "mtf_ema_period", 50))
        last_close = float(closes.iloc[-2])
        last_ema = float(ema_mtf.iloc[-2])

        if last_close > last_ema:
            return {"status": "BULLISH", "last_close": last_close, "ema": last_ema}
        else:
            return {"status": "BEARISH", "last_close": last_close, "ema": last_ema}

    def evaluate(
        self,
        df_5m: pd.DataFrame,
        df_mtf: Optional[pd.DataFrame] = None,
        required_adx: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Mengevaluasi DataFrame 5m dengan dukungan konfirmasi Multi-Timeframe (1 Jam) & Ambang ADX Seasonality.
        Mengembalikan sinyal ('BUY', 'SELL', 'HOLD') beserta metadata pendukung.
        """
        min_candles = max(self.config.ema_slow_period, self.config.rsi_period) + 5
        if len(df_5m) < min_candles:
            return {
                "signal": "HOLD",
                "reason": "Data candle 5m belum cukup untuk kalkulasi indikator.",
                "current_price": 0.0,
            }

        # Data candle 5 menit
        prev_candle = df_5m.iloc[-3]
        closed_candle = df_5m.iloc[-2]
        live_candle = df_5m.iloc[-1]

        current_price = float(live_candle["close"])
        curr_fast = float(closed_candle["ema_fast"])
        curr_slow = float(closed_candle["ema_slow"])
        prev_fast = float(prev_candle["ema_fast"])
        prev_slow = float(prev_candle["ema_slow"])
        curr_rsi = float(closed_candle["rsi"])
        prev_rsi = float(prev_candle["rsi"])
        curr_atr = float(closed_candle["atr"])

        curr_adx = float(closed_candle.get("adx", 25.0))
        curr_vol = float(closed_candle.get("volume", 0.0))
        curr_vol_sma = float(closed_candle.get("volume_sma", curr_vol))
        adx_thresh = required_adx if required_adx is not None else getattr(self.config, "adx_threshold", 20.0)
        enable_vol = getattr(self.config, "enable_volume_filter", True)
        vol_factor = getattr(self.config, "volume_factor", 0.85)

        bb_upper = float(closed_candle.get("bb_upper", current_price * 1.02))
        bb_lower = float(closed_candle.get("bb_lower", current_price * 0.98))
        bb_mid = float(closed_candle.get("bb_middle", current_price))

        # Deteksi Crossover
        golden_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        death_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)

        # Evaluasi Tren Makro (1H)
        macro = self.evaluate_macro_trend(df_mtf)
        macro_trend = macro["status"]

        # Cek apakah filter MTF aktif
        use_mtf = getattr(self.config, "use_mtf_filter", True)

        # -------------------------------------------------------------
        # 1. LOGIKA BELI (LONG / BUY)
        # -------------------------------------------------------------
        # Syarat Utama:
        # a) Golden Cross terkonfirmasi ATAU Pullback diskon di lower Bollinger Band dengan momentum naik
        # b) RSI sehat (40 <= RSI <= 70)
        # c) Tren Makro 1H WAJIB BULLISH (jika MTF aktif)
        # d) ADX >= 20 (Anti-Sideways)
        # e) Volume >= 85% Volume SMA 20 (Anti-Fakeout)
        is_bullish_pullback = (closed_candle["low"] <= bb_lower * 1.002 or curr_rsi <= 42.0) and (curr_fast > curr_slow) and (curr_rsi > prev_rsi)
        long_condition = (golden_cross or is_bullish_pullback) and (40.0 <= curr_rsi <= self.config.rsi_overbought)

        if long_condition:
            if use_mtf and macro_trend == "BEARISH":
                # Tolak sinyal beli jika tren 1 Jam masih turun (menyelamatkan dari false pump)
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal BUY ditolak: Tren Makro 1H masih BEARISH (Anti-Counter-Trend Filter)",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            if curr_adx < adx_thresh:
                # Tolak sinyal jika pasar sideways tanpa tren jelas
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal BUY ditolak: Pasar sideways/choppy (ADX {curr_adx:.1f} < {adx_thresh:.1f}). Menghindari resiko whipsaw.",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            if enable_vol and curr_vol_sma > 0 and curr_vol < (curr_vol_sma * vol_factor):
                # Tolak sinyal jika volume transaksi terlalu sepi / kering
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal BUY ditolak: Volume candle rendah ({curr_vol:.1f} < {curr_vol_sma * vol_factor:.1f}). Anti-Fakeout Filter.",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            trigger_type = "Golden Cross" if golden_cross else "Bollinger Band Pullback"
            return {
                "signal": "BUY",
                "action": "OPEN_LONG",
                "reason": (
                    f"{trigger_type}! 5m EMA Fast ({curr_fast:.4f}) > Slow ({curr_slow:.4f}) | "
                    f"RSI: {curr_rsi:.1f} | ADX: {curr_adx:.1f} (Tren Kuat) | Makro 1H: {macro_trend} ✅"
                ),
                "current_price": current_price,
                "ema_fast": curr_fast,
                "ema_slow": curr_slow,
                "rsi": curr_rsi,
                "atr": curr_atr,
                "adx": curr_adx,
                "volume": curr_vol,
                "macro_trend": macro_trend,
            }

        # -------------------------------------------------------------
        # 2. LOGIKA JUAL (SHORT / SELL)
        # -------------------------------------------------------------
        # Syarat Utama:
        # a) Death Cross terkonfirmasi ATAU Overbought di upper Bollinger Band dengan momentum turun
        # b) RSI sehat (30 <= RSI <= 60)
        # c) Tren Makro 1H WAJIB BEARISH (jika MTF aktif)
        # d) ADX >= 20 (Anti-Sideways)
        # e) Volume >= 85% Volume SMA 20 (Anti-Fakeout)
        is_bearish_pullback = (closed_candle["high"] >= bb_upper * 0.998 or curr_rsi >= 58.0) and (curr_fast < curr_slow) and (curr_rsi < prev_rsi)
        short_condition = (death_cross or is_bearish_pullback) and (self.config.rsi_oversold <= curr_rsi <= 60.0)

        if short_condition:
            if use_mtf and macro_trend == "BULLISH":
                # Tolak sinyal sell jika tren 1 Jam masih naik (menyelamatkan dari shorting di bull run)
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal SELL ditolak: Tren Makro 1H masih BULLISH (Anti-Counter-Trend Filter)",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            if curr_adx < adx_thresh:
                # Tolak sinyal jika pasar sideways tanpa tren jelas
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal SELL ditolak: Pasar sideways/choppy (ADX {curr_adx:.1f} < {adx_thresh:.1f}). Menghindari resiko whipsaw.",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            if enable_vol and curr_vol_sma > 0 and curr_vol < (curr_vol_sma * vol_factor):
                # Tolak sinyal jika volume transaksi terlalu sepi / kering
                return {
                    "signal": "HOLD",
                    "action": "FILTERED",
                    "reason": f"Sinyal SELL ditolak: Volume candle rendah ({curr_vol:.1f} < {curr_vol_sma * vol_factor:.1f}). Anti-Fakeout Filter.",
                    "current_price": current_price,
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "rsi": curr_rsi,
                    "adx": curr_adx,
                    "macro_trend": macro_trend,
                }

            trigger_type = "Death Cross" if death_cross else "Bollinger Band Rejection"
            return {
                "signal": "SELL",
                "action": "OPEN_SHORT",
                "reason": (
                    f"{trigger_type}! 5m EMA Fast ({curr_fast:.4f}) < Slow ({curr_slow:.4f}) | "
                    f"RSI: {curr_rsi:.1f} | ADX: {curr_adx:.1f} (Tren Kuat) | Makro 1H: {macro_trend} ✅"
                ),
                "current_price": current_price,
                "ema_fast": curr_fast,
                "ema_slow": curr_slow,
                "rsi": curr_rsi,
                "atr": curr_atr,
                "adx": curr_adx,
                "volume": curr_vol,
                "macro_trend": macro_trend,
            }

        # -------------------------------------------------------------
        # 3. KONDISI HOLD (TIDAK ADA SINYAL)
        # -------------------------------------------------------------
        trend_status = "BULLISH" if curr_fast > curr_slow else "BEARISH"
        return {
            "signal": "HOLD",
            "action": "WAIT",
            "reason": (
                f"Menunggu setup. Tren 5m: {trend_status} | RSI: {curr_rsi:.1f} | "
                f"ADX: {curr_adx:.1f} | Makro 1H: {macro_trend}"
            ),
            "current_price": current_price,
            "ema_fast": curr_fast,
            "ema_slow": curr_slow,
            "rsi": curr_rsi,
            "atr": curr_atr,
            "adx": curr_adx,
            "volume": curr_vol,
            "macro_trend": macro_trend,
        }
