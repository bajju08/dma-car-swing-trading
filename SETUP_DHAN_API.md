# Dhan API Setup Guide – Step by Step

## What is Dhan API?

Dhan provides a REST API to fetch historical market data, live quotes, and place orders for NSE/BSE stocks. It's free for Dhan account holders.

## Prerequisites

- You must have a **Dhan trading account** (dematerialized)
- Enable **API access** in your account (no extra charge)
- Basic understanding of API keys and tokens

---

## Step-by-Step Setup

### Step 1: Log into Dhan Web Portal

1. Go to [Dhan website](https://dhan.co) and log in with your credentials
2. Navigate to **Profile** → **API Access** or **Developer Settings**
   (If you don't see this, contact Dhan support to enable API for your account)

### Step 2: Generate API Credentials

In the API Access section, you'll see options to:

1. **Create New App / API Key**
   - App Name: `DMA_DMA_CAR_Trader` (or any name)
   - Permissions: Check these boxes:
     - ✅ `market_data` – for reading OHLC, volume, indicators
     - ✅ `order` – if you ever want auto-trading (optional for now)
     - ✅ `trade` – to fetch order status (optional)
   - Redirect URI: `http://localhost:8080` (for auth callback – we'll use this)
   - Click **Create**

2. You will get:
   - **Client ID** (your Dhan client ID, usually a number)
   - **API Key** (a long alphanumeric string)
   - **Secret Key** (a secret string – keep it safe, never share)

   **Write these down in a secure place.**

3. **Generate Access Token**:
   - Dhan uses OAuth2. You need to exchange your `client_id`, `api_key`, `secret` for an `access_token`.
   - The `access_token` expires every 24 hours. For GitHub Actions automation, we need to refresh it daily.

   **Manual method (one-time for testing)**:
   - Use Postman or curl to call:
     ```bash
     curl -X POST https://api.dhan.co/v2/rest/oauth/access_token \
       -H "Content-Type: application/json" \
       -d '{
         "client_id": "YOUR_CLIENT_ID",
         "client_secret": "YOUR_SECRET",
         "grant_type": "client_credentials"
       }'
     ```
   - Response: `{"access_token":"eyJhbGciOiJIUzI1NiJ9...","status":"success"}`
   - Copy the `access_token` value.

   **Better method (for automation)**:
   - We'll write a Python script `get_dhan_token.py` that does this daily before fetching data.
   - You'll store `client_id`, `api_key`, `secret` in `config_local.yaml` (never commit to Git).
   - The script will fetch a fresh token each time it runs.

### Step 3: Test Connection

After filling in `config_local.yaml`:

```bash
# Test if Dhan API works
python src/data_fetcher.py --test-connection
```

Expected output:
```
✅ Dhan connection successful
✅ Retrieved daily data for RELIANCE
✅ Database updated
```

If you get errors:
- Invalid credentials → double-check client_id, api_key, secret
- API not enabled → contact Dhan support
- Network issues → ensure your IP isn't blocked

---

## Alternative: Use yfinance (No API Key Needed)

If Dhan API proves difficult, the platform automatically falls back to **yfinance** (Yahoo Finance) which provides good NSE data for free.

yfinance limitations:
- ~2-second delay per stock (slower for 500 stocks)
- Limited to 2500 requests/day (but we batch)
- May miss some NSE-specific data (like delivery %)

**To use yfinance only**:
- Leave `dhan.client_id` and `dhan.api_key` empty in `config_local.yaml`
- Platform will use yfinance automatically

---

## Security Best Practices

1. **Never commit `config_local.yaml` to Git**. Add it to `.gitignore`:
   ```gitignore
   # Local config with secrets
   config_local.yaml
   *.env
   ```

2. **Use GitHub Secrets** for GitHub Actions automation:
   - In your GitHub repo: Settings → Secrets and variables → Actions
   - Add:
     - `DHAN_CLIENT_ID`
     - `DHAN_API_KEY`
     - `DHAN_SECRET`
     - `DHAN_ACCESS_TOKEN` (optional – script can fetch fresh)

3. **Rotate tokens** periodically (every 30-90 days) for security.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Invalid client_id" | Check you copied correctly, no spaces |
| "API not enabled" | Contact Dhan support: support@dhan.co |
| "Rate limit exceeded" | Dhan has limits – we batch requests, add delay |
| "Access token expired" | Our script auto-refreshes; if manual, re-run `get_dhan_token.py` |
| "Symbol not found" | Use format: `NSE:RELIANCE` (NSE: prefix mandatory) |
| "No data for date" | Data may not be available for that day (holiday) |

---

## Files You'll Edit

1. `config_local.yaml` (create from `config.yaml` template) – add your Dhan credentials
2. `.env` (auto-generated) – stores access token temporarily
3. `data/trades.csv` – your trade journal (manual entries)

---

## Next Steps

After setting up Dhan API:

1. **Test data fetch**:
   ```bash
   python src/data_fetcher.py --tickers "NSE:RELIANCE,NSE:TCS" --days 10
   ```

2. **Run initial download** for Nifty 500:
   ```bash
   python src/data_fetcher.py --full-scan
   ```
   This will take ~15-30 minutes (500 stocks × 5 years).

3. **Verify database**:
   ```bash
   python -c "from src.utils import get_db; db=get_db(); print(db.tables())"
   ```

4. **Run screener**:
   ```bash
   python src/screener.py --output recommendations.json
   ```

5. **Start dashboard**:
   ```bash
   streamlit run src/dashboard.py
   ```

6. **Set up GitHub Actions** (for daily automation) – see `SETUP_DEPLOYMENT.md`

---

## Support

- Dhan API Docs: https://docs.dhan.co/
- Dhan Support: support@dhan.co or 91-87505-87505
- Our issues: Create an issue in this GitHub repo

---

## Quick Reference Card

| Field | Where to find |
|-------|--------------|
| Client ID | Dhan web → Profile → API Access |
| API Key | Same page, after creating app |
| Secret Key | Same page, shown once – copy immediately |
| Access Token | Get via `get_dhan_token.py` script (we provide) or Postman |

**Tip**: Test with small batch first (2-3 stocks) before full Nifty 500 scan.
