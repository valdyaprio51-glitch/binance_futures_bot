"""
risk_manager.py
Modul manajemen risiko dan penyesuaian presisi order untuk Binance Futures.
Menghitung ukuran posisi (position sizing), batas Take Profit, Stop Loss,
serta memvalidasi filter LOT_SIZE, PRICE_FILTER, dan MIN_NOTIONAL.
"""

import math
from typing import Dict, Any, Tuple


class RiskManager:
    def __init__(self, config):
        self.config = config

    @staticmethod
    def round_step_size(quantity: float, step_size: float) -> float:
        """Membulatkan kuantitas ke bawah sesuai stepSize Binance."""
        if step_size <= 0:
            return quantity
        precision = int(round(-math.log10(step_size)))
        factor = 10 ** precision
        return math.floor(quantity * factor) / factor

    @staticmethod
    def round_tick_size(price: float, tick_size: float) -> float:
        """Membulatkan harga sesuai tickSize Binance."""
        if tick_size <= 0:
            return price
        precision = int(round(-math.log10(tick_size)))
        return round(price, precision)

    def calculate_position_size(
        self,
        balance_usdt: float,
        current_price: float,
        symbol_info: Dict[str, Any],
    ) -> Tuple[float, float, str]:
        """
        Menghitung kuantitas order yang aman berdasarkan risiko saldo dan leverage.
        Mengembalikan: (quantity, margin_usdt, status_message)
        """
        if current_price <= 0:
            return 0.0, 0.0, "Harga tidak valid (<= 0)"

        # Tentukan margin USDT yang dialokasikan
        if self.config.fixed_usdt_per_trade > 0:
            margin_usdt = self.config.fixed_usdt_per_trade
        else:
            margin_usdt = balance_usdt * (self.config.risk_per_trade_percent / 100.0)

        # Cek apakah margin melebihi saldo yang tersedia
        if margin_usdt > balance_usdt:
            return (
                0.0,
                0.0,
                f"Margin yang dibutuhkan ({margin_usdt:.2f} USDT) melebihi saldo ({balance_usdt:.2f} USDT).",
            )

        # Total nilai posisi dengan leverage (Notional Value)
        notional_value = margin_usdt * self.config.leverage
        raw_quantity = notional_value / current_price

        # Ekstrak filter dari Binance exchangeInfo
        step_size = symbol_info.get("step_size", 0.001)
        min_qty = symbol_info.get("min_qty", 0.001)
        min_notional = symbol_info.get("min_notional", 5.0)

        # Bulatkan ke step size yang diizinkan exchange
        quantity = self.round_step_size(raw_quantity, step_size)

        # 1. Validasi & Adaptasi batas minimal kuantitas (misal BTCUSDT min_qty = 0.001)
        if quantity < min_qty:
            min_margin_needed = (min_qty * current_price) / self.config.leverage
            # Izinkan penyesuaian jika margin yang dibutuhkan <= 25% saldo dompet
            if min_margin_needed <= (balance_usdt * 0.25):
                quantity = min_qty
                margin_usdt = min_margin_needed
            else:
                return (
                    0.0,
                    0.0,
                    f"Kuantitas ({quantity}) di bawah batas minimum Binance ({min_qty}). Butuh margin {min_margin_needed:.2f} USDT.",
                )

        # 2. Validasi & Adaptasi batas minimal notional (nilai order dalam USDT, misal BTCUSDT = 50 USDT)
        actual_notional = quantity * current_price
        if actual_notional < min_notional:
            precision = int(round(-math.log10(step_size))) if step_size > 0 else 3
            factor = 10 ** precision
            req_qty = math.ceil((min_notional / current_price) * factor) / factor
            req_margin = (req_qty * current_price) / self.config.leverage
            if req_margin <= (balance_usdt * 0.25):
                quantity = req_qty
                margin_usdt = req_margin
                actual_notional = quantity * current_price
            else:
                return (
                    0.0,
                    0.0,
                    f"Nilai order ({actual_notional:.2f} USDT) di bawah batas minimum Binance ({min_notional} USDT).",
                )

        return quantity, margin_usdt, "OK"

    def calculate_tp_sl(
        self,
        side: str,
        entry_price: float,
        tick_size: float,
    ) -> Tuple[float, float]:
        """
        Menghitung harga Stop Loss dan Take Profit berdasarkan persen yang ditentukan.
        side: 'BUY' (LONG) atau 'SELL' (SHORT)
        """
        sl_pct = self.config.stop_loss_percent / 100.0
        tp_pct = self.config.take_profit_percent / 100.0

        if side.upper() == "BUY":
            # Posisi LONG: SL di bawah entry, TP di atas entry
            raw_sl = entry_price * (1.0 - sl_pct)
            raw_tp = entry_price * (1.0 + tp_pct)
        else:
            # Posisi SHORT: SL di atas entry, TP di bawah entry
            raw_sl = entry_price * (1.0 + sl_pct)
            raw_tp = entry_price * (1.0 - tp_pct)

        sl_price = self.round_tick_size(raw_sl, tick_size)
        tp_price = self.round_tick_size(raw_tp, tick_size)

        return sl_price, tp_price

