"""
binance_client.py
Wrapper untuk komunikasi dengan Binance Futures API (USDT-M).
Mengatur autentikasi, testnet vs live, pengambilan data pasar, saldo,
manajemen leverage/margin, serta eksekusi order (Market, SL, TP).
"""

import time
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from dns_resolver import enable_doh_patch

enable_doh_patch()

logger = logging.getLogger("BinanceFuturesBot")


class BinanceFuturesClient:
    def __init__(self, config):
        self.config = config
        self.client: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        """Inisialisasi Binance Client dengan mode Testnet atau Live."""
        try:
            if self.config.use_testnet:
                logger.info("Menginisialisasi koneksi ke Binance Futures TESTNET...")
                self.client = Client(
                    api_key=self.config.api_key,
                    api_secret=self.config.api_secret,
                    testnet=True,
                )
            else:
                logger.warning("PERINGATAN: Menginisialisasi koneksi ke Binance Futures LIVE / PRODUCTION!")
                self.client = Client(
                    api_key=self.config.api_key,
                    api_secret=self.config.api_secret,
                )

            # Cache exchange_info agar inisialisasi cepat dan hemat bandwidth
            self._cached_exchange_info = None

            # Sinkronisasi timestamp dengan server Binance untuk mencegah error -1021
            self._sync_time()
        except Exception as e:
            logger.error(f"Gagal menginisialisasi Binance Client: {e}")
            raise

    def _sync_time(self):
        """Menghitung selisih waktu antara mesin lokal dan server Binance."""
        try:
            import time
            server_res = self.client.futures_time()
            server_time = server_res["serverTime"]
            local_time = int(time.time() * 1000)
            self.client.timestamp_offset = server_time - local_time
            logger.info(f"Sinkronisasi waktu Binance berhasil (offset: {self.client.timestamp_offset} ms).")
            return True
        except Exception as e:
            logger.warning(f"Gagal menyelaraskan waktu dengan server Binance: {e}")
            return False

    def refresh_connection(self) -> bool:
        """
        Memulihkan sesi koneksi dan menyelaraskan ulang waktu dengan server Binance.
        Dipanggil otomatis jika terputus jaringan atau setelah laptop bangun dari sleep.
        """
        logger.info("Memperbarui sesi koneksi dan menyelaraskan ulang jam server...")
        try:
            if hasattr(self.client, "session") and self.client.session:
                try:
                    self.client.session.close()
                except Exception:
                    pass
                self.client.session = self.client._init_session()

            return self._sync_time()
        except Exception as e:
            logger.warning(f"Gagal memulihkan sesi: {e}")
            return False

    def get_account_balance(self) -> float:
        """Mengambil saldo USDT yang tersedia di wallet Futures."""
        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b.get("availableBalance", b.get("balance", 0.0)))
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Error mengambil saldo Futures: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error koneksi saat mengambil saldo: {e}")
            raise

    def get_pnl_summary(self) -> Dict[str, Any]:
        """
        Mengambil rekapitulasi performa PnL, komisi fee, dan riwayat modal masuk
        langsung dari Binance Futures API secara akurat.
        """
        try:
            incomes = self.client.futures_income_history(limit=1000)
            total_transfers = sum(float(i.get("income", 0.0)) for i in incomes if i.get("incomeType") == "TRANSFER")
            realized_pnl = sum(float(i.get("income", 0.0)) for i in incomes if i.get("incomeType") == "REALIZED_PNL")
            commission = sum(float(i.get("income", 0.0)) for i in incomes if i.get("incomeType") == "COMMISSION")
            funding_fee = sum(float(i.get("income", 0.0)) for i in incomes if i.get("incomeType") == "FUNDING_FEE")

            acc = self.client.futures_account()
            total_wallet = float(acc.get("totalWalletBalance", 0.0))
            available = float(acc.get("availableBalance", 0.0))
            unrealized_pnl = float(acc.get("totalUnrealizedProfit", 0.0))

            net_pnl = realized_pnl + commission + funding_fee
            net_pct = (net_pnl / total_transfers * 100.0) if total_transfers > 0 else 0.0

            return {
                "total_transfers": total_transfers,
                "total_wallet": total_wallet,
                "available": available,
                "unrealized_pnl": unrealized_pnl,
                "realized_pnl": realized_pnl,
                "commission": commission,
                "funding_fee": funding_fee,
                "net_pnl": net_pnl,
                "net_pct": net_pct,
            }
        except Exception as e:
            logger.warning(f"Gagal mengambil rekapitulasi PnL: {e}")
            bal = self.get_account_balance()
            return {
                "total_transfers": bal,
                "total_wallet": bal,
                "available": bal,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "commission": 0.0,
                "funding_fee": 0.0,
                "net_pnl": 0.0,
                "net_pct": 0.0,
            }

    def setup_margin_and_leverage(self, symbol: str):
        """Mengatur margin type (ISOLATED/CROSSED) dan leverage untuk simbol yang dipilih."""
        # 1. Atur Margin Type
        try:
            self.client.futures_change_margin_type(
                symbol=symbol,
                marginType=self.config.margin_type,
            )
            logger.info(f"Margin Type untuk {symbol} berhasil diatur ke {self.config.margin_type}.")
        except BinanceAPIException as e:
            # Kode -4046 artinya margin type sudah sesuai, abaikan
            if e.code == -4046:
                logger.info(f"Margin Type untuk {symbol} sudah {self.config.margin_type}.")
            else:
                logger.warning(f"Gagal mengatur Margin Type ({e.code}): {e.message}")

        # 2. Atur Leverage
        try:
            res = self.client.futures_change_leverage(
                symbol=symbol,
                leverage=self.config.leverage,
            )
            logger.info(f"Leverage untuk {symbol} berhasil diatur ke {res.get('leverage', self.config.leverage)}x.")
        except BinanceAPIException as e:
            logger.error(f"Gagal mengatur Leverage ({e.code}): {e.message}")
            raise

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Mengambil informasi filter presisi harga, step size, dan batas minimal notional."""
        try:
            if self._cached_exchange_info is None:
                self._cached_exchange_info = self.client.futures_exchange_info()
            exchange_info = self._cached_exchange_info
            symbol_data = None
            for s in exchange_info["symbols"]:
                if s["symbol"] == symbol:
                    symbol_data = s
                    break

            if not symbol_data:
                raise ValueError(f"Simbol {symbol} tidak ditemukan di Binance Futures.")

            info = {
                "symbol": symbol,
                "step_size": 0.001,
                "min_qty": 0.001,
                "tick_size": 0.1,
                "min_notional": 5.0,
            }

            for f in symbol_data.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    info["step_size"] = float(f["stepSize"])
                    info["min_qty"] = float(f["minQty"])
                elif f["filterType"] == "PRICE_FILTER":
                    info["tick_size"] = float(f["tickSize"])
                elif f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
                    info["min_notional"] = float(f.get("notional", f.get("minNotional", 5.0)))

            return info
        except Exception as e:
            logger.error(f"Gagal mengambil symbol info untuk {symbol}: {e}")
            raise

    def get_klines_df(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """Mengambil data candlestick historis dan mengonversinya ke Pandas DataFrame."""
        try:
            raw_klines = self.client.futures_klines(
                symbol=symbol,
                interval=timeframe,
                limit=limit,
            )
            cols = [
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_base_vol",
                "taker_quote_vol", "ignore"
            ]
            df = pd.DataFrame(raw_klines, columns=cols)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df
        except Exception as e:
            logger.error(f"Gagal mengambil klines untuk {symbol}: {e}")
            raise

    def get_current_position(self, symbol: str) -> Dict[str, Any]:
        """
        Mengambil informasi posisi aktif saat ini untuk simbol terkait.
        Mengembalikan dictionary posisi: amt, side ('LONG', 'SHORT', 'NONE'), entry_price, unRealizedProfit, dll.
        """
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for p in positions:
                if p["symbol"] == symbol:
                    amt = float(p.get("positionAmt", 0.0))
                    entry_price = float(p.get("entryPrice", 0.0))
                    pnl = float(p.get("unRealizedProfit", 0.0))
                    liq_price = float(p.get("liquidationPrice", 0.0))

                    if amt > 0:
                        side = "LONG"
                    elif amt < 0:
                        side = "SHORT"
                    else:
                        side = "NONE"

                    return {
                        "symbol": symbol,
                        "side": side,
                        "amount": abs(amt),
                        "raw_amount": amt,
                        "entry_price": entry_price,
                        "unrealized_pnl": pnl,
                        "liquidation_price": liq_price,
                        "leverage": int(p.get("leverage", self.config.leverage)),
                    }

            return {"symbol": symbol, "side": "NONE", "amount": 0.0, "raw_amount": 0.0, "entry_price": 0.0, "unrealized_pnl": 0.0}
        except Exception as e:
            logger.error(f"Gagal mengambil posisi untuk {symbol}: {e}")
            raise

    def cancel_all_orders(self, symbol: str):
        """Membatalkan seluruh open conditional orders (misal sisa SL/TP)."""
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            logger.info(f"Semua open orders untuk {symbol} telah dibatalkan.")
        except BinanceAPIException as e:
            logger.warning(f"Gagal membatalkan open orders ({e.code}): {e.message}")
        except Exception as e:
            logger.error(f"Error koneksi saat cancel orders: {e}")

    def execute_market_order(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """
        Mengeksekusi Market Order.
        side: 'BUY' (untuk Open Long atau Close Short) atau 'SELL' (untuk Open Short atau Close Long)
        """
        try:
            logger.info(f"Mengirim MARKET ORDER: {side} {quantity} {symbol}...")
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side.upper(),
                type="MARKET",
                quantity=quantity,
            )
            logger.info(f"Market order berhasil dieksekusi! Order ID: {order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Gagal eksekusi market order ({e.code}): {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error eksekusi market order: {e}")
            raise

    def place_stop_loss_order(self, symbol: str, position_side: str, stop_price: float, retry_on_conflict: bool = True) -> Optional[Dict[str, Any]]:
        """
        Menempatkan order Stop Loss (STOP_MARKET) dengan fitur closePosition=True.
        position_side: 'LONG' (order jual untuk tutup) atau 'SHORT' (order beli untuk tutup).
        Memiliki fitur Auto-Recovery jika terkena error -4130 (order gantung duplikat).
        """
        order_side = "SELL" if position_side.upper() == "LONG" else "BUY"
        try:
            logger.info(f"Menempatkan STOP LOSS di harga {stop_price} (Side: {order_side})...")
            order = self.client.futures_create_order(
                symbol=symbol,
                side=order_side,
                type="STOP_MARKET",
                stopPrice=stop_price,
                closePosition=True,
            )
            logger.info(f"Stop Loss order terpasang! ID: {order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            if e.code == -4130 and retry_on_conflict:
                logger.warning(
                    f"Terdeteksi order proteksi konflik (-4130) untuk {symbol}. "
                    f"Membersihkan order lama di arah {order_side} dan memasang ulang Stop Loss..."
                )
                try:
                    open_orders = self.client.futures_get_open_orders(symbol=symbol)
                    for o in open_orders:
                        o_type = o.get("type", "")
                        o_side = o.get("side", "")
                        if o_side == order_side and (
                            o.get("closePosition") is True 
                            or o_type in ("STOP_MARKET", "STOP", "STOP_LOSS", "TRAILING_STOP_MARKET")
                        ):
                            try:
                                self.client.futures_cancel_order(symbol=symbol, orderId=o["orderId"])
                                logger.info(f"Order konflik lama {symbol} (ID: {o['orderId']}, Type: {o_type}) dibatalkan.")
                            except Exception:
                                pass
                    time.sleep(0.5)  # Beri jeda ke Binance matching engine agar order lama benar-benar bersih
                    # Pasang ulang SL
                    retry_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=order_side,
                        type="STOP_MARKET",
                        stopPrice=stop_price,
                        closePosition=True,
                    )
                    logger.info(f"[AUTO-RECOVERY] Stop Loss {symbol} BERHASIL dipasang setelah pembersihan order konflik! ID: {retry_order.get('orderId')}")
                    return retry_order
                except Exception as retry_err:
                    logger.error(f"[AUTO-RECOVERY GAGAL] Tidak dapat memasang Stop Loss {symbol}: {retry_err}")
                    return None
            else:
                logger.error(f"Gagal memasang Stop Loss ({e.code}): {e.message}")
                return None
        except Exception as e:
            logger.error(f"Error memasang Stop Loss: {e}")
            return None

    def place_take_profit_order(self, symbol: str, position_side: str, tp_price: float, retry_on_conflict: bool = True) -> Optional[Dict[str, Any]]:
        """
        Menempatkan order Take Profit (TAKE_PROFIT_MARKET) dengan fitur closePosition=True.
        position_side: 'LONG' (order jual untuk tutup) atau 'SHORT' (order beli untuk tutup).
        Memiliki fitur Auto-Recovery jika terkena error -4130.
        """
        order_side = "SELL" if position_side.upper() == "LONG" else "BUY"
        try:
            logger.info(f"Menempatkan TAKE PROFIT di harga {tp_price} (Side: {order_side})...")
            order = self.client.futures_create_order(
                symbol=symbol,
                side=order_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=tp_price,
                closePosition=True,
            )
            logger.info(f"Take Profit order terpasang! ID: {order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            if e.code == -4130 and retry_on_conflict:
                logger.warning(
                    f"Terdeteksi order TP konflik (-4130) untuk {symbol}. "
                    f"Membersihkan order lama di arah {order_side} dan memasang ulang Take Profit..."
                )
                try:
                    open_orders = self.client.futures_get_open_orders(symbol=symbol)
                    for o in open_orders:
                        o_type = o.get("type", "")
                        o_side = o.get("side", "")
                        if o_side == order_side and (
                            o.get("closePosition") is True 
                            or o_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT")
                        ):
                            try:
                                self.client.futures_cancel_order(symbol=symbol, orderId=o["orderId"])
                                logger.info(f"Order TP konflik lama {symbol} (ID: {o['orderId']}, Type: {o_type}) dibatalkan.")
                            except Exception:
                                pass
                    time.sleep(0.5)
                    retry_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=order_side,
                        type="TAKE_PROFIT_MARKET",
                        stopPrice=tp_price,
                        closePosition=True,
                    )
                    logger.info(f"[AUTO-RECOVERY] Take Profit {symbol} BERHASIL dipasang kembali! ID: {retry_order.get('orderId')}")
                    return retry_order
                except Exception as retry_err:
                    logger.error(f"[AUTO-RECOVERY GAGAL] Tidak dapat memasang Take Profit {symbol}: {retry_err}")
                    return None
            else:
                logger.error(f"Gagal memasang Take Profit ({e.code}): {e.message}")
                return None
        except Exception as e:
            logger.error(f"Error memasang Take Profit: {e}")
            return None

    def move_stop_loss(self, symbol: str, position_side: str, new_stop_price: float, label: str = "Break-Even") -> bool:
        """
        Memindahkan Stop Loss yang ada ke harga baru (Break-Even atau Trailing Stop).
        Membatalkan STOP_MARKET lama secara bersih dan memasang STOP_MARKET baru di harga new_stop_price.
        """
        order_side = "SELL" if position_side.upper() == "LONG" else "BUY"
        try:
            open_orders = self.client.futures_get_open_orders(symbol=symbol)
            canceled_count = 0
            for o in open_orders:
                o_type = o.get("type", "")
                o_side = o.get("side", "")
                if o_side == order_side and (
                    o.get("closePosition") is True or o_type in ("STOP_MARKET", "STOP", "STOP_LOSS", "TRAILING_STOP_MARKET")
                ):
                    try:
                        self.client.futures_cancel_order(symbol=symbol, orderId=o["orderId"])
                        logger.info(f"Order SL lama untuk {symbol} (ID: {o['orderId']}) dibatalkan untuk geser ke {label}.")
                        canceled_count += 1
                    except Exception as ce:
                        logger.warning(f"Gagal cancel order {o.get('orderId')}: {ce}")

            if canceled_count > 0:
                time.sleep(0.4)  # Beri jeda ke Binance matching engine agar order lama benar-benar bersih

            # Pasang SL baru di harga new_stop_price
            res = self.place_stop_loss_order(symbol, position_side, new_stop_price)
            return res is not None
        except Exception as e:
            logger.error(f"Gagal memindahkan Stop Loss ke {label} untuk {symbol}: {e}")
            return False

    def move_stop_loss_to_breakeven(self, symbol: str, position_side: str, entry_price: float) -> bool:
        """Memindahkan Stop Loss yang ada ke harga Entry (Break-Even)."""
        return self.move_stop_loss(symbol, position_side, entry_price, label="Break-Even")

