# DMA-DMA+CAR Institutional Swing Trading Platform

An institutional-grade, automated swing trading system for NSE stocks, based on the DMA-DMA + CAR strategy enhanced with multiple filters for high win-rate signals.

## Features

- **Automated Data Pipeline**: Fetch NSE data via Dhan API (or yfinance fallback)
- **Enhanced Screener**: Ranks Nifty 500 stocks with Conviction Score (0-15), Speed Score (0-10), and Master Signal
- **Market Regime Detection**: Adaptive position sizing based on overall market health
- **Trade Journal**: Manual entry with auto P&L tracking, average management, target recalculation
- **Daily Alerts**: Telegram & Email notifications by 9 AM IST with top picks
- **TradingView Indicator**: Pine Script v6 for chart-based signals
- **Backtesting Engine**: Historical simulation with parameter optimization
- **Cloud-Ready**: Deploy on Streamlit Cloud (free) or any VPS
- **Mobile Responsive**: Works great on phone browsers

## Quick Start

### 1. Setup Environment

```bash
cd trading
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Dhan API (Optional) or Use yfinance

Edit `config_local.yaml`:

```yaml
dhan:
  client_id: "YOUR_CLIENT_ID"
  api_key: "YOUR_API_KEY"
  secret: "YOUR_SECRET"

telegram:
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
```

If you don't fill Dhan fields, system uses yfinance (no credentials needed).

### 3. Test Connection

```bash
python src/screener.py --test-dhan
```

### 4. Run Daily Screener

```bash
python src/screener.py --full-update  # First time (fetches 5 years of data)
python src/screener.py               # Subsequent runs (incremental)
```

Output: `recommendations.json`

### 5. Launch Dashboard

```bash
streamlit run src/dashboard.py
```

Open browser to `http://localhost:8501`

### 6. Import TradingView Indicator

1. Open Pine Editor in TradingView
2. Copy contents of `src/indicator.pine`
3. Paste, save, and add to chart
4. Set your entry price and scores manually

---

## Project Structure

```
trading/
├── config.yaml                 # Default config template (DO NOT EDIT)
├── config_local.yaml           # Your personal config (ADD TO .gitignore)
├── requirements.txt
├── README.md
│
├── SETUP_DHAN_API.md           # Detailed Dhan API guide
├── SETUP_TELEGRAM.md           # Telegram bot setup
├── SETUP_DEPLOYMENT.md         # Deploy to cloud (Streamlit Cloud + GitHub Actions)
├── STRATEGY_GUIDE.md           # Complete strategy rules and enhancements
│
├── data/
│   └── market_data.db         # SQLite database (auto-created)
│
├── src/
│   ├── utils.py               # Utilities
│   ├── data_fetcher.py        # Dhan API + yfinance
│   ├── indicators.py          # Technical indicators (DMA, RSI, CAR, Beta, etc.)
│   ├── strategy.py            # Scoring engine and market regime
│   ├── screener.py            # CLI to run daily scan
│   ├── dashboard.py           # Streamlit web dashboard
│   ├── alerts.py              # Telegram & Email
│   └── indicator.pine         # TradingView Pine Script v6
│
├── scripts/
│   └── daily.sh                # Cron script template
│
├── .github/
│   └── workflows/
│       └── daily.yml           # GitHub Actions (auto-run 8:30 AM IST)
│
├── notebooks/
│   └── analysis.ipynb          # EDA and backtesting
│
├── Sheet3.csv                  # Nifty 500 tickers (provided)
├── DMA_CAR_Strategy_Document_v2.docx  # Original strategy doc
├── DMA_CAR_Enhanced_500.xlsx   # Your Google Sheets tracker
├── CAR Formula.txt             # Your formulas
├── recommendations.json        # Output from screener (auto-generated)
└── strategy_transcripts.json   # YouTube transcripts (reference)

```

---

## Daily Workflow

1. **Morning (8:30-9:00 AM IST)**:
   - GitHub Actions runs automatically (if deployed)
   - Data refreshed, screener runs
   - Telegram alert sent with top 10 picks
   - `recommendations.json` updated in repo

2. **You check alerts** on phone (Telegram)

3. **Morning trading** (9:15 AM - 3:30 PM):
   - Open dashboard (Streamlit Cloud URL)
   - Check top picks, market regime
   - If favorable signal, execute trade manually via broker app
   - Immediately log trade in dashboard (Trade Entry page)

4. **During hold**:
   - Dashboard auto-updates current prices (refresh page)
   - Watch for target hit alerts or Bear Run warnings
   - If price drops ≥10% and CAR="Buy/Average Out" → average weekly (Wednesdays) as per rules
   - Use "Trades" page to add average (click ➕ button)

5. **Exit**:
   - When price hits 6.28% target → book profit
   - Close trade in dashboard (or mark CLOSED manually)
   - 50% of after-tax profit reinvests in next chain slot

6. **Evening**:
   - Dashboard shows updated P&L
   - 30-day review reminders appear
   - Regime analysis for next day

---

## Cloud Deployment (Free)

1. **Push code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial"
   git remote add origin https://github.com/yourname/dma-dma-car.git
   git push -u origin main
   ```

2. **Deploy Dashboard to Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - New app → select repo → main branch → src/dashboard.py
   - Add Secrets: `DHAN_CLIENT_ID`, `DHAN_API_KEY`, `DHAN_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - Deploy

3. **Automate Daily Screener with GitHub Actions**
   - Already included: `.github/workflows/daily.yml`
   - Set repository secrets in GitHub Settings → Secrets and variables → Actions
   - Add: `DHAN_CLIENT_ID`, `DHAN_API_KEY`, `DHAN_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - The workflow runs daily at 08:30 IST and updates `recommendations.json`

4. **Done** – your Streamlit app auto-refreshes from the updated JSON, and you get Telegram alerts every morning.

---

## Strategy Rules at a Glance

| Component | Rules |
|-----------|-------|
| **Entry** | Price > 50, 100, 200 DMA (Bull Run) AND Golden DMA (50>100>200) AND Enhanced Score ≥8 (adjust by regime) |
| **Conviction Score (0-10)** | Golden (3) + Distance from 200 DMA (0-4) + CAR signal (2) + Data OK (1) |
| **Enhanced Score (0-15)** | Conviction (0-10) + Volume ≥1.2x (1) + Beta ≥0.8 (1) + RS >0% (1) + 52wk Zone (1) + EPS+ (1) |
| **Speed Score (0-10)** | Derived from beta, volume, RS, zone – higher = faster to target |
| **Position Size** | FULL_BULL: 100%, CAUTIOUS: 75%, REDUCED: 50%, PAUSE: 0% |
| **Target** | 6.28% from average price (entry price * 1.0628 or after averaging) |
| **Averaging** | When price ≥10% below entry/last avg AND CAR="Buy/Average Out" AND still in Bull Run. Max 14 times. Every Wednesday. Amount = initial_slot/15 |
| **Exit** | 1. Target hit (book profit). 2. Max 180 days. 3. Bear Run >60 days + CAR=Avoid = exit at loss |
| **Market Regime** | Based on % of Nifty 500 in Bull Run: FULL_BULL (≥15%), CAUTIOUS (7-15%), REDUCED, PAUSE |

---

## Backtesting & Optimization

Run from command line:

```bash
python src/backtest.py --start 2021-01-01 --end 2025-12-31 --capital 15000
```

Output:
- Total returns, CAGR
- Win rate, profit factor
- Max drawdown
- Sharpe ratio
- Average days to target

Optimization:
```bash
python src/optimizer.py --start 2021-01-01 --end 2025-12-31
```

Will grid-search over thresholds and recommend optimal parameters.

---

## Files You Must Provide/Customize

1. `config_local.yaml` – Your Dhan API keys, Telegram, Email (copy from config.yaml template)
2. `Sheet3.csv` – Nifty 500 tickers (you already have)
3. `DMA_CAR_Enhanced_500.xlsx` – Your existing Google Sheet for reference (not used by platform)

---

## Support & Documentation

- **Dhan API Setup**: See `SETUP_DHAN_API.md`
- **Telegram Setup**: See `SETUP_TELEGRAM.md`
- **Deployment**: See `SETUP_DEPLOYMENT.md`
- **Strategy Details**: See `STRATEGY_GUIDE.md` and `DMA_CAR_Strategy_Document_v2.docx`
- **YouTube Transcripts**: See `strategy_transcripts.json` (original strategy foundation)

---

## License & Disclaimer

For educational purposes. Not financial advice. Trade at your own risk.

---

## Version

**v1.0 Institutional** – Built March 2026

---

## Next Steps

1. Fill `config_local.yaml` with your Dhan and Telegram credentials
2. Run `python src/screener.py --test-dhan` to verify data connection
3. Run first full scan: `python src/screener.py --full-update`
4. Start dashboard: `streamlit run src/dashboard.py`
5. Set up Telegram bot (if not done)
6. (Optional) Push to GitHub and deploy to Streamlit Cloud for 24/7 access
7. Daily check Telegram at 9 AM, trade, log in dashboard

**Enjoy your institutional swing trading platform!** 🚀
