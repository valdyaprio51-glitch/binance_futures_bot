"""
power_manager.py
Manajemen daya sistem Windows untuk menjaga bot tetap berjalan:
1. Mencegah Windows otomatis Sleep/Suspended saat bot aktif (layar tetap bisa mati hemat daya).
2. Memulihkan pengaturan daya default saat bot dimatikan.
"""

import sys
import logging

logger = logging.getLogger("BinanceFuturesBot")


def prevent_sleep():
    """Memberi tahu Windows agar tidak otomatis Sleep saat bot berjalan."""
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        # Mengatur thread execution state agar sistem tetap terjaga
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        logger.info("Proteksi Windows Sleep Aktif (Laptop tidak akan otomatis sleep saat bot berjalan).")
    except Exception as e:
        logger.debug(f"Gagal mengatur SetThreadExecutionState: {e}")


def allow_sleep():
    """Mengembalikan aturan sleep bawaan Windows saat bot dihentikan."""
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass

