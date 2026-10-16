"""
seasonality.py
Modul Analisis Intraday Seasonality untuk Binance Futures Trading Bot:
1. Identifikasi Sesi Jam Perdagangan Global (Asia, London Open, New York Prime Overlap, dan Pacific Dead Zone).
2. Proteksi Waktu Settlement Funding Fee Binance (00:00, 08:00, 16:00 UTC).
3. Ambang batas ADX adaptif untuk memfilter pergerakan sideways saat likuiditas tipis.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Tuple


class IntradaySeasonality:
    def __init__(self, config):
        self.config = config

    def get_current_session(self, now_utc: datetime = None) -> Dict[str, Any]:
        """
        Menganalisis sesi pasar global saat ini berdasarkan jam UTC dan WIB.
        - London Open (07:00 - 13:00 UTC / 14:00 - 20:00 WIB)
        - New York Prime (13:00 - 21:00 UTC / 20:00 - 04:00 WIB)
        - Dead Zone (21:00 - 24:00 UTC / 04:00 - 07:00 WIB)
        - Asia Session (00:00 - 07:00 UTC / 07:00 - 14:00 WIB)
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        hour = now_utc.hour
        minute = now_utc.minute
        minute_of_day = hour * 60 + minute
        wib_hour = (hour + 7) % 24

        if 13 <= hour < 21:
            session_name = "NEW_YORK_PRIME"
            session_label = "Sesi New York (Peak Vol & Trend)"
            is_prime = True
            is_dead_zone = False
        elif 7 <= hour < 13:
            session_name = "LONDON_OPEN"
            session_label = "Sesi London / Eropa (Likuiditas Tinggi)"
            is_prime = True
            is_dead_zone = False
        elif 21 <= hour < 24:
            session_name = "DEAD_ZONE"
            session_label = "Dead Zone / Pasifik (Order Book Tipis, Rawan Chop)"
            is_prime = False
            is_dead_zone = True
        else:
            session_name = "ASIA_SESSION"
            session_label = "Sesi Asia (Volume Moderat, Cenderung Sideways)"
            is_prime = False
            is_dead_zone = False

        # Jendela Settlement Funding Fee Binance (00:00, 08:00, 16:00 UTC)
        # Buffer: 10 menit sebelum s/d 5 menit sesudah jam settlement
        funding_windows = [
            (23 * 60 + 50, 24 * 60), (0, 5),     # 00:00 UTC / 07:00 WIB
            (7 * 60 + 50, 8 * 60 + 5),           # 08:00 UTC / 15:00 WIB
            (15 * 60 + 50, 16 * 60 + 5),         # 16:00 UTC / 23:00 WIB
        ]
        is_funding_window = any(start_m <= minute_of_day <= end_m for start_m, end_m in funding_windows)

        return {
            "session_name": session_name,
            "session_label": session_label,
            "is_prime": is_prime,
            "is_dead_zone": is_dead_zone,
            "is_funding_window": is_funding_window,
            "utc_time": f"{hour:02d}:{minute:02d} UTC",
            "wib_time": f"{wib_hour:02d}:{minute:02d} WIB",
        }

    def check_trade_allowed(self) -> Tuple[bool, str, float]:
        """
        Memvalidasi apakah pembukaan posisi baru diizinkan berdasarkan siklus sesi saat ini.
        Mengembalikan: (is_allowed, reason, required_adx)
        """
        if not getattr(self.config, "enable_seasonality_filter", True):
            return True, "Filter Seasonality Nonaktif", self.config.adx_threshold

        sess = self.get_current_session()

        # 1. Cek Proteksi Settlement Funding Fee (10 menit sebelum jam 07:00, 15:00, 23:00 WIB)
        if getattr(self.config, "avoid_funding_settlement", True) and sess["is_funding_window"]:
            return (
                False,
                f"Jendela Settlement Funding Fee ({sess['wib_time']}). Menunda entry baru untuk menghindari potongan fee & spread spike.",
                self.config.adx_threshold,
            )

        # 2. Cek Dead Zone (04:00 - 07:00 WIB / 21:00 - 00:00 UTC)
        if sess["is_dead_zone"]:
            if getattr(self.config, "block_dead_zone", True):
                return (
                    False,
                    f"Sesi Dead Zone ({sess['wib_time']}). Order book tipis dan rawan whipsaw. Menunggu pembukaan sesi Asia.",
                    self.config.adx_threshold,
                )
            else:
                # Jika tidak diblokir total, naikkan syarat ADX menjadi lebih ketat
                strict_adx = max(self.config.adx_threshold, 26.0)
                return True, f"Sesi Dead Zone (Strict ADX {strict_adx})", strict_adx

        # 3. Cek Sesi Asia (07:00 - 14:00 WIB) -> Naikkan standar ADX sedikit untuk anti-sideways
        if sess["session_name"] == "ASIA_SESSION":
            asia_adx = getattr(self.config, "asia_adx_minimum", 22.0)
            target_adx = max(self.config.adx_threshold, asia_adx)
            return (
                True,
                f"Sesi Asia ({sess['wib_time']}) - Mode Anti-Sideways (ADX minimal {target_adx})",
                target_adx,
            )

        # 4. Sesi Prime (London & New York: 14:00 - 04:00 WIB) -> Likuiditas optimal
        return (
            True,
            f"{sess['session_label']} ({sess['wib_time']}) - Likuiditas Optimal",
            self.config.adx_threshold,
        )

