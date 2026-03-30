# Deployment Guide – Free Cloud Setup

Deploy your DMA-DMA+CAR platform for 24/7 access with automated daily runs and mobile-friendly dashboard.

---

## Option 1: Streamlit Cloud + GitHub Actions (RECOMMENDED – Free)

This gives you:
- Dashboard always online (free)
- Automated daily screener (free via GitHub Actions)
- Database persisted in GitHub repo
- Access from phone/any device

### Step 1: Create GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name repo: `dma-dma-car`
3. Check: "Add a README file" (optional)
4. Create repository

### Step 2: Clone and Push Code

```bash
cd "C:\Users\bhara\OneDrive\Desktop\Trading"
git init
git add .
# Create .gitignore
echo "config_local.yaml" > .gitignore
echo ".env" >> .gitignore
echo "data/market_data.db" >> .gitignore
echo "recommendations.json" >> .gitignore
git add .gitignore
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/dma-dma-car.git
git push -u origin main
```

### Step 3: Add Repository Secrets

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

| Name | Value |
|------|-------|
| `DHAN_CLIENT_ID` | Your Dhan client ID (from Dhan API portal) |
| `DHAN_API_KEY` | Your Dhan API key |
| `DHAN_SECRET` | Your Dhan secret |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID (from @userinfobot) |

**Note**: If you prefer to use yfinance only (no Dhan), you can skip Dhan secrets.

### Step 4: Configure GitHub Actions Workflow

The file `.github/workflows/daily.yml` already exists. Edit if needed:

```yaml
# Runs daily at 8:30 AM IST (03:00 UTC)
on:
  schedule:
    - cron: '0 3 * * *'  # 3:00 AM UTC = 8:30 AM IST (UTC+5:30)
  workflow_dispatch:  # Allow manual trigger

jobs:
  daily-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run Screener
        env:
          DHAN_CLIENT_ID: ${{ secrets.DHAN_CLIENT_ID }}
          DHAN_API_KEY: ${{ secrets.DHAN_API_KEY }}
          DHAN_SECRET: ${{ secrets.DHAN_SECRET }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          python src/screener.py --full-update   # first run only
          # For daily after, use just: python src/screener.py
      - name: Commit results
        run: |
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git config --global user.name "github-actions[bot]"
          git add recommendations.json
          git commit -m "Daily update $(date +'%Y-%m-%d')" || echo "No changes"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**First run**: Change `--full-update` to fetch all historical data (takes 30min). Subsequent daily runs use only `--full-update` removed (incremental).

### Step 5: Deploy Dashboard to Streamlit Cloud

1. Go to [Streamlit Cloud](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app** → select your repo → `main` branch
4. Main file path: `src/dashboard.py`
5. Click **Advanced settings** → **Secrets** and add:

```json
{
  "dhan": {
    "client_id": "YOUR_CLIENT_ID",
    "api_key": "YOUR_API_KEY",
    "secret": "YOUR_SECRET"
  },
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

6. Click **Deploy**

Your dashboard will be live at: `https://yourusername-dma-dma-car-xxxx.streamlit.app`

### Step 6: Test Everything

1. Open your Streamlit app URL
2. Click **Home** page → **Refresh Data** button
3. It will trigger a screener run (takes 5-15 min for 500 stocks)
4. Check `recommendations.json` in your GitHub repo gets updated
5. You receive a Telegram message with top picks
6. Dashboard shows results

### Step 7: Schedule GitHub Actions (Already Configured)

The `daily.yml` workflow runs every day at 8:30 AM IST.
It updates `recommendations.json` in your repo.

Streamlit Cloud automatically reloads when the file changes, so your dashboard always shows latest.

---

## Option 2: Local + Cloud Storage (Simpler, but Less Auto)

If GitHub Actions seems complex, use a simpler approach:

1. **Run screener manually** each evening on your laptop:
   ```bash
   python src/screener.py --full-update
   ```
   Save `recommendations.json` to Google Drive

2. **Open HTML viewer** on phone:
   - Create a simple HTML file that reads `recommendations.json` from Drive and displays nicely
   - Open that HTML in phone browser

3. **Manual trade journal** in CSV on Drive

This avoids cloud compute entirely. But less automation.

---

## Option 3: VPS (Paid, $5/mo)

If you want full control:
- Rent a DigitalOcean droplet ($5/mo)
- SSH in, clone repo, set up systemd service to run daily
- Deploy Streamlit on port 8501, reverse proxy with nginx
- Use system cron for scheduling

---

## Monitoring & Maintenance

### Check Screener Logs
- GitHub Actions: repo → Actions tab → latest workflow → logs

### Clear Database
If DB grows large (> several GB):
```bash
python -c "from src.utils import get_db_engine; engine=get_db_engine(); engine.execute('DELETE FROM market_data WHERE date < date(''2023-01-01'')')"
```

### Update Nifty 500 List
If constituents change:
1. Get updated list from NSE website
2. Replace `Sheet3.csv`
3. Run `--full-update` to fetch data for new tickers

---

## Troubleshooting

### GitHub Actions Fails
- Check secrets are set correctly
- Look at workflow logs for specific error
- If Dhan API rate limit, switch to yfinance by clearing Dhan secrets and using fallback

### Streamlit Cloud App Crashes
- Check logs in Streamlit Cloud dashboard
- Ensure `config_local.yaml` and secrets are set (Streamlit uses Secrets, not config_local.yaml)
- Reduce memory by limiting scan to fewer stocks temporarily

### No Telegram Alerts
- Verify bot token and chat ID
- Test with `python src/alerts.py --test-telegram` (locally)
- Ensure bot privacy mode is OFF in @BotFather settings (allows sending to non-chat first)

### Data Missing for Some Stocks
- Dhan API may not have tickers for some small caps
- Fallback to yfinance fills most gaps
- Some stocks may be delisted – ignore

---

## Moving to Production

For real trading, consider:
- Dedicated VPS for reliability
- Separate PostgreSQL (vs SQLite) for concurrent access
- Encrypted backup of database
- More robust error handling and notification on failures
- Two-tier alerts: Telegram + SMS backup (Twilio)
- Daily health check email

---

## Cost Summary (Yearly)

| Service | Cost |
|---------|------|
| Streamlit Cloud | Free (with limitations) |
| GitHub Actions | Free (2,000 min/month) |
| Data | Free (Dhan or yfinance) |
| **Total** | **₹0** |

If you hit GitHub Actions limits (~2k minutes/month), upgrade to paid (around $0.008 per minute) but 500 stocks daily takes ~15-20 min, well under free limit.

---

## Next Up

Now that the platform is built, your daily routine:
1. Wake up, check Telegram for picks (8:30-9:00 AM)
2. Open dashboard on phone, review top picks
3. Trade manually in broker app
4. Log trade in dashboard → auto tracks P&L
5. Close at target → repeat

**You now have an institutional-grade, automated swing trading system running 100% free in the cloud.**

Enjoy! 🎉
