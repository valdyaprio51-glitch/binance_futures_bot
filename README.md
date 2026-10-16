# Binance Futures Institutional Quantitative Trading Bot (Python)

Bot trading kuantitatif algoritmik otomatis untuk **Binance Futures (USDT-Margined)** level institusional yang dibangun menggunakan Python. Bot ini mendukung posisi **LONG** dan **SHORT**, multi-pair paralel (hingga 11+ koin), pertahanan risiko berlapis (*Multi-Timeframe, ADX, Volume Filter, Intraday Seasonality*), penguncian profit dinamis (*Tiered Trailing Stop*), serta kebal sensor jaringan (*DNS-over-HTTPS*) dan *Anti-Sleep Windows*.

---

## 🌟 Fitur Utama (Institutional Grade)

1. **Multi-Pair Concurrent Scanning (11 Koin Utama)**:
   - Memindai secara berkala: `BTC`, `ETH`, `SOL`, `BNB`, `SUI`, `NEAR`, `AVAX`, `DOGE`, `APT`, `RENDER`, dan `1000PEPE`.
   - Mengelola maksimal posisi aktif paralel secara aman tanpa overtrading (`MAX_ACTIVE_POSITIONS=3`).

2. **Pertahanan Berlapis & Filter Probabilitas Tinggi**:
   - **Multi-Timeframe Trend Confirmation (1H EMA 50)**: Sinyal 5m hanya dieksekusi jika searah dengan tren makro 1 Jam (*Anti-Counter-Trend*).
   - **Filter Kekuatan Tren ADX (Anti-Sideways)**: Menolak sinyal ketika pasar sedang sideways/choppy ($\text{ADX} < 20$).
   - **Filter Volume Dinamis (Anti-Fakeout)**: Memastikan volume transaksi candle minimal 85% dari rata-rata 20 candle.
   - **Bollinger Bands Pullback + RSI Confirmation**: Menangkap titik pantulan harga di zona diskon/support.

3. **Intraday Seasonality & Global Session Engine**:
   - **Sesi Asia (07:00 – 14:00 WIB)**: Mode adaptif anti-sideways (ADX minimal dinaikkan otomatis ke 22).
   - **Sesi London & New York (14:00 – 04:00 WIB)**: Mode likuiditas penuh untuk menangkap tren besar institusi dunia.
   - **Dead Zone Pacific (04:00 – 07:00 WIB)**: Menahan pembukaan posisi baru untuk mencegah *whipsaw* saat likuiditas tipis.
   - **Anti-Funding Settlement Window**: Menahan entry 10 menit sebelum jam settlement funding fee Binance (07:00, 15:00, 23:00 WIB).

4. **Tiered Trailing Stop (Kunci Profit Bertahap 3 Tingkat)**:
   - **Tier 1 (+0.6% Profit)**: Stop Loss otomatis digeser ke harga modal + buffer fee (Posisi 100% bebas risiko modal).
   - **Tier 2 (+1.2% Profit)**: Stop Loss digeser mengunci profit separuh di **+0.6%**.
   - **Tier 3 (+1.6% Profit)**: Stop Loss digeser mengunci profit aman di **+1.0%**.
   - **Full Take Profit**: Tetap siap mengeksekusi target maksimal di **+2.0%**.

5. **Ketahanan Sistem 24/7 & Bypass Sensor Jaringan**:
   - **DNS-over-HTTPS (DoH)**: Bypass pemblokiran DNS ISP lokal (TrustPositif / Kominfo) via Cloudflare & Google DNS.
   - **Windows Anti-Sleep (`power_manager.py`)**: Layar laptop boleh mati atau ditutup, CPU dan jaringan bot tetap aktif.
   - **Resiliensi Dynamic IP**: Auto-retry dan auto-resync saat terjadi rotasi IP seluler Telkomsel atau putus koneksi sesaat.

6. **Live Financial Tracker & PnL Audit di Terminal**:
   - Menampilkan total modal masuk, saldo dompet terkini, komisi fee, gross PnL, dan net profit/loss bersih secara transparan.

---

## 📁 Struktur Direktori

```text
binance_futures_bot/
│
├── config.py           # Manajemen konfigurasi environment dataclass
├── binance_client.py   # Wrapper API Binance Futures (auth, orders, PnL tracker)
├── indicators.py       # Perhitungan teknikal murni (EMA, RSI, ATR, BB, ADX)
├── strategy.py         # Logika strategi kuantitatif, pullback & filter tren
├── seasonality.py      # Analisis Intraday Seasonality & filter jam sesi dunia
├── risk_manager.py     # Position sizing, presisi exchange, kalkulasi SL/TP
├── dns_resolver.py     # DNS-over-HTTPS (DoH) Cloudflare & Google resolver
├── power_manager.py    # Windows execution state keeper (anti-sleep)
├── main.py             # Lifecycle loop bot & event handler
├── requirements.txt    # Daftar dependensi Python
├── .env.example        # Template konfigurasi bot
└── README.md           # Dokumentasi lengkap
```

---

## 🚀 Panduan Instalasi & Menjalankan

### 1. Clone & Masuk ke Folder Project
```bash
git clone https://github.com/valdyaprio51-glitch/binance_futures_bot.git
cd binance_futures_bot
```

### 2. Siapkan Virtual Environment & Dependensi
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / Mac / Termux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Konfigurasi File `.env`
Salin template konfigurasi:
```bash
cp .env.example .env
```
Buka file `.env` dan masukkan API Key serta API Secret Binance Futures Anda:
```env
BINANCE_API_KEY=api_key_anda_di_sini
BINANCE_API_SECRET=api_secret_anda_di_sini
USE_TESTNET=false
```

### 4. Jalankan Bot
```bash
python main.py
```

---

## ⚠️ Disclaimer
Trading aset kripto derivatif / futures mengandung risiko finansial. Pastikan Anda memahami manajemen risiko modal dan selalu gunakan dana dingin (*risk capital*). Bot ini disediakan untuk tujuan otomasi strategi kuantitatif.
