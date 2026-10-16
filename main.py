"""
main.py
Program utama untuk menjalankan Binance Futures Multi-Trade Trading Bot
dengan Fitur Kuantitatif Profesional:
1. Multi-Timeframe Alignment (1H EMA 50 Trend Filter)
2. Bollinger Bands + RSI Pullback (High-Probability Entry)
3. Auto Break-Even Protection (Kunci Modal Bebas Risiko saat floating profit >= +0.6%)
4. Multi-Pair Concurrent Trading (Maks 2 posisi aktif)
5. Anti-Sleep & Sleep-Resilient Auto Recovery (Tahan sleep, auto-reconnect, auto-resync)
"""

import sys
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from colorama import init, Fore, Style

from dns_resolver import enable_doh_patch
from power_manager import prevent_sleep, allow_sleep

# Aktifkan patch DNS-over-HTTPS untuk bypass ISP sinkhole/pemblokiran lokal
enable_doh_patch()

from config import config
from binance_client import BinanceFuturesClient
from indicators import add_indicators
from strategy import EmaRsiStrategy
from risk_manager import RiskManager
from seasonality import IntradaySeasonality
from binance.exceptions import BinanceAPIException, BinanceRequestException

# Inisialisasi colorama untuk warna output terminal
init(autoreset=True)

# Konfigurasi format logging
logging.basicConfig(
    level=logging.INFO,
    format=f"{Fore.WHITE}[%(asctime)s]{Style.RESET_ALL} %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BinanceFuturesBot")


def print_banner(pnl_data: Dict[str, Any], seasonality: IntradaySeasonality):
    """Menampilkan banner informatif status bot dan kinerja keuangan akun."""
    mode_str = f"{Fore.GREEN}TESTNET (DEMO)" if config.use_testnet else f"{Fore.RED}LIVE / PRODUCTION (UANG NYATA)"
    symbols_str = ", ".join(config.symbols)
    be_str = (
        f"{Fore.GREEN}AKTIF (T1: +{config.trailing_tier1_profit}%->BE, T2: +{config.trailing_tier2_profit}%->+{config.trailing_tier2_lock}%, T3: +{config.trailing_tier3_profit}%->+{config.trailing_tier3_lock}%){Style.RESET_ALL}"
        if config.enable_trailing_stop
        else (f"{Fore.GREEN}AKTIF (+{config.break_even_trigger_percent}% trigger){Style.RESET_ALL}" if config.enable_break_even else f"{Fore.YELLOW}NONAKTIF{Style.RESET_ALL}")
    )
    mtf_str = f"{Fore.GREEN}AKTIF ({config.mtf_timeframe} EMA {config.mtf_ema_period}){Style.RESET_ALL}" if config.use_mtf_filter else f"{Fore.YELLOW}NONAKTIF{Style.RESET_ALL}"
    filter_str = (
        f"{Fore.GREEN}ADX >= {config.adx_threshold:.0f} (Anti-Sideways) + Vol Filter {config.volume_factor*100:.0f}% (Anti-Fakeout){Style.RESET_ALL}"
        if config.enable_volume_filter
        else f"{Fore.GREEN}ADX >= {config.adx_threshold:.0f}{Style.RESET_ALL}"
    )

    sess = seasonality.get_current_session()
    sess_str = (
        f"{Fore.GREEN}{sess['session_label']} ({sess['wib_time']}){Style.RESET_ALL}"
        if config.enable_seasonality_filter
        else f"{Fore.YELLOW}NONAKTIF{Style.RESET_ALL}"
    )

    total_trans = pnl_data.get("total_transfers", 0.0)
    wallet_bal = pnl_data.get("total_wallet", 0.0)
    realized_val = pnl_data.get("realized_pnl", 0.0)
    fee_val = pnl_data.get("commission", 0.0)
    net_val = pnl_data.get("net_pnl", 0.0)
    net_pct = pnl_data.get("net_pct", 0.0)

    pnl_color = Fore.GREEN if net_val >= 0 else Fore.RED
    realized_color = Fore.GREEN if realized_val >= 0 else Fore.RED

    print("\n" + "=" * 78)
    print(f"{Fore.CYAN}{Style.BRIGHT}        BINANCE FUTURES PRO QUANTITATIVE BOT (INSTITUTIONAL GRADE)        {Style.RESET_ALL}")
    print("=" * 78)
    print(f" Mode            : {mode_str}{Style.RESET_ALL}")
    print(f" Simbol Pantauan : {Fore.YELLOW}{symbols_str}{Style.RESET_ALL}")
    print(f" Maks Posisi     : {Fore.CYAN}{config.max_active_positions} posisi aktif bersamaan{Style.RESET_ALL}")
    print(f" Timeframe Trade : {config.timeframe} (Scalp)")
    print(f" Sesi Pasar      : {sess_str}")
    print(f" Filter Makro    : {mtf_str}")
    print(f" Filter Sideways : {filter_str}")
    print(f" Trailing Stop   : {be_str}")
    print(f" Anti-Sleep PC   : {Fore.GREEN}AKTIF (Layar bisa mati, sistem bot tetap terjaga){Style.RESET_ALL}")
    print("-" * 78)
    print(f"{Fore.YELLOW}{Style.BRIGHT} [REKAP KINERJA KEUANGAN / PNL TRACKER AKUN]{Style.RESET_ALL}")
    print(f" Modal Ditransfer: {Fore.WHITE}{total_trans:.2f} USDT (~Rp {int(total_trans * 16400):,}){Style.RESET_ALL}")
    print(f" Saldo Dompet    : {Fore.GREEN if wallet_bal >= total_trans else Fore.YELLOW}{wallet_bal:.2f} USDT (~Rp {int(wallet_bal * 16400):,}){Style.RESET_ALL}")
    print(f" Hasil Trading   : {realized_color}{realized_val:+.2f} USDT (Gross Realized PnL){Style.RESET_ALL}")
    print(f" Biaya Komisi    : {Fore.RED}{fee_val:+.2f} USDT (Fee Maker/Taker Binance){Style.RESET_ALL}")
    print(f" Net PnL Bersih  : {pnl_color}{Style.BRIGHT}{net_val:+.2f} USDT ({net_pct:+.2f}% dari modal){Style.RESET_ALL}")
    print("-" * 78)
    print(f" Leverage        : {config.leverage}x ({config.margin_type})")
    print(f" Risiko Trade    : {config.risk_per_trade_percent}% per posisi (~{(wallet_bal * config.risk_per_trade_percent / 100):.2f} USDT margin)")
    print(f" SL / TP         : SL = {config.stop_loss_percent}%, TP = {config.take_profit_percent}% (R:R 1:2)")
    print(f" Strategi        : EMA Cross (9/21) + RSI (14) + BB (20/2) + ADX (14) + Seasonality")
    print("=" * 78 + "\n")


def main():
    # 1. Validasi konfigurasi
    try:
        config.validate()
    except ValueError as ve:
        print(f"\n{Fore.RED}[ERROR KONFIGURASI]{Style.RESET_ALL}")
        print(ve)
        print(f"\n{Fore.YELLOW}Silakan periksa file .env terlebih dahulu!{Style.RESET_ALL}\n")
        sys.exit(1)

    # 2. Inisialisasi Modul & Proteksi Sleep
    prevent_sleep()

    strategy = EmaRsiStrategy(config)
    risk_mgr = RiskManager(config)
    seasonality = IntradaySeasonality(config)

    max_init_retries = 6
    client = None
    balance = 0.0

    for attempt in range(1, max_init_retries + 1):
        try:
            client = BinanceFuturesClient(config)
            balance = client.get_account_balance()
            break
        except BinanceAPIException as bae:
            if bae.code == -2015:
                logger.warning(
                    f"{Fore.YELLOW}[KONEKSI IP DINAMIS / -2015] (Percobaan {attempt}/{max_init_retries}): {bae.message}{Style.RESET_ALL}\n"
                    f"{Fore.CYAN}Menunggu 3 detik untuk perputaran IP... (Tips: Ubah IP Restriction ke 'Unrestricted' di Binance jika sering muncul){Style.RESET_ALL}"
                )
                if attempt == max_init_retries:
                    logger.error(f"Inisialisasi bot gagal setelah {max_init_retries} percobaan: {bae}")
                    allow_sleep()
                    sys.exit(1)
                time.sleep(3)
            else:
                logger.error(f"Inisialisasi bot gagal: {bae}")
                allow_sleep()
                sys.exit(1)
        except Exception as e:
            logger.error(f"Inisialisasi bot gagal: {e}")
            allow_sleep()
            sys.exit(1)

    pnl_summary = client.get_pnl_summary()
    print_banner(pnl_summary, seasonality)

    # Setup leverage, margin type, dan ambil exchange filters untuk semua koin
    symbols_info = {}
    for sym in config.symbols:
        try:
            client.setup_margin_and_leverage(sym)
            symbols_info[sym] = client.get_symbol_info(sym)
            logger.info(
                f"Filter Simbol {sym}: StepSize={symbols_info[sym]['step_size']}, "
                f"TickSize={symbols_info[sym]['tick_size']}, MinNotional={symbols_info[sym]['min_notional']} USDT"
            )
        except Exception as e:
            logger.warning(f"Peringatan setup margin {sym}: {e}")
            symbols_info[sym] = client.get_symbol_info(sym)

    # 3. Main Loop
    logger.info(f"Bot kuantitatif aktif memantau {len(config.symbols)} koin. Tekan Ctrl+C untuk berhenti.\n")

    last_signals = {}
    last_positions_state = {}
    breakeven_locked = set()
    trailing_tier_locked = {}
    last_season_block = ""

    try:
        while True:
            try:
                # 1. Cek Posisi Aktif Saat Ini untuk Semua Koin
                current_positions = {}
                for sym in config.symbols:
                    pos = client.get_current_position(sym)
                    if pos["side"] != "NONE":
                        current_positions[sym] = pos
                    else:
                        # Jika sebelumnya ada posisi dan sekarang NONE, posisi telah closed di Binance
                        if sym in last_positions_state:
                            logger.info(f"{Fore.MAGENTA}Posisi {sym} telah selesai/ditutup (TP atau SL tercapai)!{Style.RESET_ALL}")
                            client.cancel_all_orders(sym)
                            breakeven_locked.discard(sym)
                            trailing_tier_locked.pop(sym, None)
                            try:
                                up_pnl = client.get_pnl_summary()
                                net_c = Fore.GREEN if up_pnl["net_pnl"] >= 0 else Fore.RED
                                logger.info(
                                    f"{Fore.CYAN}[UPDATE KEUANGAN / PNL]{Style.RESET_ALL} "
                                    f"Saldo Dompet: {Fore.WHITE}{up_pnl['total_wallet']:.2f} USDT{Style.RESET_ALL} | "
                                    f"Hasil Trading: {up_pnl['realized_pnl']:+.2f} USDT | "
                                    f"Net PnL: {net_c}{up_pnl['net_pnl']:+.2f} USDT ({up_pnl['net_pct']:+.2f}%){Style.RESET_ALL}"
                                )
                            except Exception:
                                pass

                last_positions_state = dict(current_positions)

                # 2. Kelola Posisi yang Sedang Aktif (Tiered Trailing Stop & Reversal)
                if current_positions:
                    for sym, pos in list(current_positions.items()):
                        pnl = pos["unrealized_pnl"]
                        pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
                        entry = pos["entry_price"]
                        pos_side = pos["side"]
                        tick_size = symbols_info[sym]["tick_size"]

                        # Ambil harga candle live untuk menghitung floating profit %
                        df_live = client.get_klines_df(sym, config.timeframe, limit=5)
                        live_price = float(df_live.iloc[-1]["close"]) if len(df_live) > 0 else entry

                        # Hitung persentase profit saat ini
                        if pos_side == "LONG":
                            profit_pct = ((live_price - entry) / entry) * 100.0 if entry > 0 else 0.0
                        else:
                            profit_pct = ((entry - live_price) / entry) * 100.0 if entry > 0 else 0.0

                        # Status Label Trailing Tier
                        curr_tier = trailing_tier_locked.get(sym, 0)
                        if curr_tier == 3:
                            tier_tag = f"{Fore.GREEN}[TIER 3 LOCKED +{config.trailing_tier3_lock}%]{Style.RESET_ALL} "
                        elif curr_tier == 2:
                            tier_tag = f"{Fore.GREEN}[TIER 2 LOCKED +{config.trailing_tier2_lock}%]{Style.RESET_ALL} "
                        elif curr_tier == 1 or sym in breakeven_locked:
                            tier_tag = f"{Fore.GREEN}[BE LOCKED]{Style.RESET_ALL} "
                        else:
                            tier_tag = f"{Fore.WHITE}[OPEN]{Style.RESET_ALL} "

                        logger.info(
                            f"{Fore.CYAN}[POSISI AKTIF - {sym}]{Style.RESET_ALL} {tier_tag}"
                            f"{Fore.YELLOW}{pos_side}{Style.RESET_ALL} {pos['amount']} {sym} | "
                            f"Entry: ${entry:.4f} | Harga: ${live_price:.4f} ({profit_pct:+.2f}%) | "
                            f"PnL: {pnl_color}{pnl:+.2f} USDT{Style.RESET_ALL} | "
                            f"Liq: ${pos['liquidation_price']:.4f}"
                        )

                        # =========================================================
                        # FITUR TIERED TRAILING STOP (KUNCI PROFIT BERTAHAP)
                        # =========================================================
                        # TIER 3: Kunci Profit +1.0% jika floating profit >= +1.6%
                        if config.enable_trailing_stop and curr_tier < 3 and profit_pct >= config.trailing_tier3_profit:
                            lock_pct = config.trailing_tier3_lock
                            raw_sl = entry * (1.0 + (lock_pct / 100.0)) if pos_side == "LONG" else entry * (1.0 - (lock_pct / 100.0))
                            new_sl = RiskManager.round_tick_size(raw_sl, tick_size)
                            logger.info(
                                f"{Fore.GREEN}{Style.BRIGHT}[TRAILING STOP TIER 3] Profit {sym} telah mencapai {profit_pct:+.2f}% "
                                f"(>= {config.trailing_tier3_profit}%)! Mengunci profit ke +{lock_pct}% (SL: ${new_sl:.4f})...{Style.RESET_ALL}"
                            )
                            if client.move_stop_loss(sym, pos_side, new_sl, label=f"Tier 3 Trailing (+{lock_pct}%)"):
                                trailing_tier_locked[sym] = 3
                                breakeven_locked.add(sym)
                                logger.info(f"{Fore.GREEN}{Style.BRIGHT}BERHASIL! Profit {sym} sebesar +{lock_pct}% telah TERKUNCI AMAN!{Style.RESET_ALL}")

                        # TIER 2: Kunci Profit +0.6% jika floating profit >= +1.2%
                        elif config.enable_trailing_stop and curr_tier < 2 and profit_pct >= config.trailing_tier2_profit:
                            lock_pct = config.trailing_tier2_lock
                            raw_sl = entry * (1.0 + (lock_pct / 100.0)) if pos_side == "LONG" else entry * (1.0 - (lock_pct / 100.0))
                            new_sl = RiskManager.round_tick_size(raw_sl, tick_size)
                            logger.info(
                                f"{Fore.GREEN}{Style.BRIGHT}[TRAILING STOP TIER 2] Profit {sym} telah mencapai {profit_pct:+.2f}% "
                                f"(>= {config.trailing_tier2_profit}%)! Mengunci separuh profit ke +{lock_pct}% (SL: ${new_sl:.4f})...{Style.RESET_ALL}"
                            )
                            if client.move_stop_loss(sym, pos_side, new_sl, label=f"Tier 2 Trailing (+{lock_pct}%)"):
                                trailing_tier_locked[sym] = 2
                                breakeven_locked.add(sym)
                                logger.info(f"{Fore.GREEN}{Style.BRIGHT}BERHASIL! Profit {sym} sebesar +{lock_pct}% telah TERKUNCI!{Style.RESET_ALL}")

                        # TIER 1: Auto Break-Even + Buffer jika floating profit >= +0.6%
                        elif (config.enable_trailing_stop or config.enable_break_even) and curr_tier < 1 and profit_pct >= config.trailing_tier1_profit:
                            lock_pct = config.trailing_tier1_lock
                            raw_sl = entry * (1.0 + (lock_pct / 100.0)) if pos_side == "LONG" else entry * (1.0 - (lock_pct / 100.0))
                            new_sl = RiskManager.round_tick_size(raw_sl, tick_size)
                            logger.info(
                                f"{Fore.GREEN}{Style.BRIGHT}[TRAILING STOP TIER 1 / BREAK-EVEN] Profit {sym} telah mencapai {profit_pct:+.2f}% "
                                f"(>= {config.trailing_tier1_profit}%)! Menggeser SL ke Entry + buffer ({lock_pct}%) (${new_sl:.4f})...{Style.RESET_ALL}"
                            )
                            if client.move_stop_loss(sym, pos_side, new_sl, label="Tier 1 Break-Even"):
                                trailing_tier_locked[sym] = 1
                                breakeven_locked.add(sym)
                                logger.info(f"{Fore.GREEN}{Style.BRIGHT}BERHASIL! Posisi {sym} sekarang 100% BEBAS RISIKO (Risk-Free Trade)!{Style.RESET_ALL}")

                        # Cek Sinyal Pembalikan Arah (Reversal Exit)
                        df = client.get_klines_df(sym, config.timeframe, limit=50)
                        df = add_indicators(df, config)
                        signal_data = strategy.evaluate(df)

                        if (pos["side"] == "LONG" and signal_data["signal"] == "SELL") or \
                           (pos["side"] == "SHORT" and signal_data["signal"] == "BUY"):
                            logger.warning(f"Terdeteksi sinyal pembalikan arah {sym} ({signal_data['signal']})! Menutup posisi aktif...")
                            close_side = "SELL" if pos["side"] == "LONG" else "BUY"
                            client.execute_market_order(sym, close_side, pos["amount"])
                            client.cancel_all_orders(sym)
                            del current_positions[sym]
                            if sym in last_positions_state:
                                del last_positions_state[sym]
                            breakeven_locked.discard(sym)
                            trailing_tier_locked.pop(sym, None)
                            logger.info(f"Posisi {sym} berhasil ditutup karena sinyal pembalikan arah.")

                # 3. Cari Peluang Trading di Koin yang Belum Memiliki Posisi Aktif
                available_slots = config.max_active_positions - len(current_positions)

                if available_slots <= 0:
                    time.sleep(config.poll_interval_seconds)
                    continue

                # Cek Filter Intraday Seasonality (Sesi Waktu Dunia & Funding Settlement)
                trade_allowed, season_reason, req_adx = seasonality.check_trade_allowed()
                if not trade_allowed:
                    if last_season_block != season_reason:
                        logger.info(f"{Fore.YELLOW}[INTRADAY SEASONALITY] Entry baru ditahan: {season_reason}{Style.RESET_ALL}")
                        last_season_block = season_reason
                    time.sleep(config.poll_interval_seconds)
                    continue
                else:
                    if last_season_block:
                        logger.info(f"{Fore.GREEN}[INTRADAY SEASONALITY] Jendela entry kembali aktif: {season_reason}{Style.RESET_ALL}")
                        last_season_block = ""

                for sym in config.symbols:
                    if sym in current_positions:
                        continue

                    if available_slots <= 0:
                        break

                    # Ambil data klines 5 menit
                    df_5m = client.get_klines_df(sym, config.timeframe, limit=80)
                    df_5m = add_indicators(df_5m, config)

                    # Ambil data klines 1 Jam jika Multi-Timeframe aktif
                    df_mtf = None
                    if config.use_mtf_filter:
                        df_mtf = client.get_klines_df(sym, config.mtf_timeframe, limit=70)

                    # Evaluasi Strategi Pro dengan ambang ADX adaptif dari Seasonality
                    signal_data = strategy.evaluate(df_5m, df_mtf, required_adx=req_adx)

                    current_price = signal_data["current_price"]
                    fast_ema = signal_data.get("ema_fast", 0.0)
                    slow_ema = signal_data.get("ema_slow", 0.0)
                    rsi = signal_data.get("rsi", 0.0)
                    adx = signal_data.get("adx", 0.0)
                    macro_t = signal_data.get("macro_trend", "N/A")
                    sig = signal_data["signal"]

                    status_summary = (
                        f"[{sym}] Harga: ${current_price:.4f} | EMA(9/21): {fast_ema:.4f}/{slow_ema:.4f} | "
                        f"RSI: {rsi:.1f} | ADX: {adx:.1f} (min {req_adx:.0f}) | Makro 1H: {macro_t} | Sinyal: {sig}"
                    )

                    if last_signals.get(sym) != sig or sig != "HOLD":
                        logger.info(status_summary)
                        last_signals[sym] = sig

                    # Eksekusi jika sinyal BUY atau SELL muncul
                    if sig in ("BUY", "SELL"):
                        logger.info(f"{Fore.GREEN}{Style.BRIGHT}[{sym}] SINYAL DITERIMA: {signal_data['action']}!{Style.RESET_ALL}")
                        logger.info(f"Alasan: {signal_data['reason']}")

                        # Ambil saldo terkini
                        balance = client.get_account_balance()
                        logger.info(f"Saldo USDT saat ini: {balance:.2f} USDT")

                        # Hitung ukuran posisi
                        sym_info = symbols_info[sym]
                        qty, margin_used, msg = risk_mgr.calculate_position_size(
                            balance_usdt=balance,
                            current_price=current_price,
                            symbol_info=sym_info,
                        )

                        if msg != "OK":
                            logger.warning(f"Order {sym} dibatalkan oleh Risk Manager: {msg}")
                        else:
                            logger.info(
                                f"Kuantitas order {sym}: {qty} (Margin: ~{margin_used:.2f} USDT, Leverage: {config.leverage}x)"
                            )

                            # Hitung TP dan SL
                            sl_price, tp_price = risk_mgr.calculate_tp_sl(
                                side=sig,
                                entry_price=current_price,
                                tick_size=sym_info["tick_size"],
                            )
                            logger.info(f"Proteksi {sym}: Stop Loss = ${sl_price} | Take Profit = ${tp_price}")

                            # 1. Batalkan sisa order lama jika ada
                            client.cancel_all_orders(sym)
                            time.sleep(0.5)

                            # 2. Eksekusi Market Order Buka Posisi
                            client.execute_market_order(
                                symbol=sym,
                                side=sig,
                                quantity=qty,
                            )

                            # Jeda 1 detik agar posisi terdaftar di sistem Binance
                            time.sleep(1)

                            # 3. Pasang Stop Loss & Take Profit Awal
                            pos_side = "LONG" if sig == "BUY" else "SHORT"
                            sl_res = client.place_stop_loss_order(sym, pos_side, sl_price)
                            time.sleep(0.5)
                            tp_res = client.place_take_profit_order(sym, pos_side, tp_price)

                            if sl_res:
                                logger.info(f"{Fore.GREEN}Proteksi Stop Loss {sym} AKTIF di ${sl_price}!{Style.RESET_ALL}")
                            else:
                                logger.error(f"{Fore.RED}{Style.BRIGHT}[PERINGATAN KRUSIAL] Stop Loss {sym} BELUM TERPASANG di bursa! Harap periksa manual!{Style.RESET_ALL}")

                            if tp_res:
                                logger.info(f"{Fore.GREEN}Target Take Profit {sym} AKTIF di ${tp_price}!{Style.RESET_ALL}")

                            logger.info(f"{Fore.GREEN}Posisi {sym} {pos_side} dan proteksi SL/TP aktif!{Style.RESET_ALL}\n")

                            # Catat ke posisi aktif saat ini
                            current_positions[sym] = {"side": pos_side, "amount": qty, "entry_price": current_price}
                            trailing_tier_locked[sym] = 0
                            available_slots -= 1

                time.sleep(config.poll_interval_seconds)

            except BinanceAPIException as bae:
                if bae.code == -1021:
                    logger.warning(
                        f"{Fore.YELLOW}[WAKTU TIDAK SINKRON (SLEEP/WAKE-UP)] "
                        f"Mereset jam server Binance dan menyelaraskan ulang...{Style.RESET_ALL}"
                    )
                    time.sleep(3)
                    client.refresh_connection()
                else:
                    logger.error(f"Binance API Exception: [{bae.code}] {bae.message}")
                    time.sleep(10)
            except BinanceRequestException as bre:
                logger.warning(
                    f"{Fore.YELLOW}[KONEKSI TERPUTUS / LAPTOP SLEEP] "
                    f"Menunggu koneksi internet tersambung kembali... ({bre}){Style.RESET_ALL}"
                )
                time.sleep(5)
                client.refresh_connection()
            except Exception as e:
                err_msg = str(e)
                # Tangani putus koneksi jaringan atau error socket setelah sleep
                net_keywords = ("connection", "timeout", "timed out", "reset", "disconnected", "getaddrinfo", "10054", "remotedisconnected")
                if any(k in err_msg.lower() for k in net_keywords):
                    logger.warning(
                        f"{Fore.YELLOW}[JARINGAN OFFLINE / LAPTOP WAKE-UP] "
                        f"Koneksi sedang pulih ({err_msg}). Memulihkan sesi bot...{Style.RESET_ALL}"
                    )
                    time.sleep(5)
                    client.refresh_connection()
                else:
                    logger.error(f"Terjadi kesalahan tidak terduga: {e}", exc_info=True)
                    time.sleep(10)

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Menerima perintah keluar (Ctrl+C). Menghentikan bot secara aman...{Style.RESET_ALL}")
    finally:
        # Kembalikan aturan daya normal Windows saat keluar
        allow_sleep()
        print(f"{Fore.CYAN}Proteksi daya dipulihkan. Bot dinonaktifkan. Terima kasih!{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
