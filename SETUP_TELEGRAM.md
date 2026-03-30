# Telegram Alert Setup Guide

## Why Telegram?

- Free, instant delivery
- Works on mobile and desktop
- Can send formatted messages with emojis
- No SMS costs
- Reliable in India

---

## Step 1: Create a Telegram Bot

1. Open Telegram app (on phone or desktop)
2. Search for **@BotFather** (official bot creator)
3. Start chat, send: `/newbot`
4. BotFather asks:
   - **Bot name**: `DMA-DMA CAR Bot` (or any name)
   - **Username**: Must end with `bot` (e.g., `DMADMACAR_bot` or `TradingAlertBot`)
5. BotFather replies with:
   - **Bot Token**: `1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789`
   - **Save this token** – it's your `telegram.bot_token`

Example token format: `7012345678:AAHcKq79s0D3mR4oT7X9Y2zAbCdEfGhIjKl`

---

## Step 2: Get Your Chat ID

Your bot needs to know where to send messages. Your "chat ID" is a number.

**Method A (easiest)**:
1. Search for your new bot in Telegram (the username you created, e.g., `@DMADMACAR_bot`)
2. Start a chat with it: send `/start`
3. In a web browser, open:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   Replace `<YOUR_BOT_TOKEN>` with your actual token from BotFather.

   Example:
   ```
   https://api.telegram.org/bot7012345678:AAHcKq79s0D3mR4oT7X9Y2zAbCdEfGhIjKl/getUpdates
   ```

4. You'll see a JSON response. Look for:
   ```json
   {
     "update_id": 123456789,
     "message": {
       "message_id": 1,
       "from": {
         "id": 987654321,
         "first_name": "Bharadwaz"
       },
       "chat": {
         "id": 987654321,
         "first_name": "Bharadwaz"
       },
       "date": 1712345678,
       "text": "/start"
     }
   }
   ```

5. The `chat.id` is **your chat ID**. In this example: `987654321`

   **Important**:
   - If your chat ID is negative (e.g., `-1001234567890`), that's a channel/group. Use that exactly.
   - For personal chat, it's usually a 9-10 digit positive number.

**Method B (alternative)**:
Send any message to the bot, then run:
```bash
python -c "import requests; r=requests.get('https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates'); print(r.json())"
```
Find `chat.id` in the output.

---

## Step 3: Add Bot Token and Chat ID to Config

Open `config_local.yaml` (you'll create this from `config.yaml`):

```yaml
telegram:
  bot_token: "7012345678:AAHcKq79s0D3mR4oT7X9Y2zAbCdEfGhIjKl"  # from BotFather
  chat_id: "987654321"  # from getUpdates (your personal chat ID)

email:
  # leave empty if not using email
```

**Save the file**.

---

## Step 4: Test Telegram Alert

```bash
# Test sending a message
python src/alerts.py --test-telegram
```

You should receive a Telegram message like:

```
🧪 DMA-DMA+CAR Platform Test

If you see this, Telegram alerts are working! ✅

Time: 2026-03-31 14:30:00
```

If you don't receive:
- Check token and chat_id are correct
- Ensure you started a chat with the bot first (send /start)
- Check internet connection

---

## Step 5: Daily Alert Schedule

Our platform will send two types of alerts:

### A. Daily Recommendations (9:00 AM IST)
- **Content**: Top 10 stocks with Enhanced Score, Speed Score, entry prices, targets
- **Format**:
  ```
  📊 DMA-DMA+CAR Daily Picks – 2026-03-31

  Market Regime: FULL BULL (18% stocks Bull Run)

  🥇 Rank 1: NSE:SONACOMS
     Enhanced: 13/15 | Speed: 9/10
     CMP: ₹521 | Target: ₹553 (6.28%)
     DMA: 50>100>200 ✅ | CAR: Buy/Average ✅

  🥈 Rank 2: NSE:SUNPHARMA
     Enhanced: 12/15 | Speed: 8/10
     ...
  ```

### B. Instant Alerts (when triggered)
- **Bull Run Signal**: When a stock enters Bull Run with score ≥8
- **Target Hit**: When price reaches 6.28%
- **CAR Change Alert**: When CAR turns "Buy/Average Out" (for existing holdings)
- **Bear Run Warning**: When stock turns Bear Run (exit signal)

---

## Step 6: GitHub Actions Setup (for Cloud Automation)

If deploying to Streamlit Cloud with GitHub Actions:

1. Add these **Secrets** in your GitHub repo:
   - Go to repo → Settings → Secrets and variables → Actions → New repository secret
   - Add: `TELEGRAM_BOT_TOKEN` = your bot token
   - Add: `TELEGRAM_CHAT_ID` = your chat ID

2. GitHub Actions workflow will use these secrets to send alerts automatically.

---

## Advanced: Multiple Recipients

If you want to send alerts to multiple people (family, friends), you can:

**Option 1: Telegram Group**
1. Create a Telegram group
2. Add your bot to the group
3. Get the group chat ID:
   - Add bot to group
   - Send a message in group
   - Check `getUpdates` – `chat.id` will be negative (e.g., `-1001234567890`)
4. Use that group chat ID in config – all group members receive alerts

**Option 2: Broadcast to multiple users** (requires storing user chat IDs)
- Modify `alerts.py` to maintain a list of chat IDs
- Loop through each and send message
- For privacy, users must first message the bot to register their chat ID (we can implement a `/subscribe` command)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Bot token is invalid" | Re-create bot with @BotFather, copy token exactly |
| "Chat not found" | Start chat with bot first, send /start |
| "Forbidden: bot was blocked" | User blocked bot → they need to unblock |
| No messages received | Check bot token, chat_id, internet; test with curl: `curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" -d "chat_id=<CHAT_ID>&text=test"` |
| Group messages fail | Bot must be added to group and have permission to post |

---

## Formatting Messages

Telegram supports **MarkdownV2** or **HTML**. Our platform uses MarkdownV2 for bold, emojis, etc.

Example message format (auto-generated):
```markdown
📈 **DMA-DMA+CAR Alert** 🚨

Stock: *NSE:RELIANCE*
Signal: **BUY** 🟢
Target: ₹2,800 (6.28% from ₹2,635)
```

---

## Privacy & Security

- Your bot token is like a password. Anyone with it can send messages to your chat.
- Never share the token publicly (GitHub commits, screenshots).
- If token leaks, re-create the bot with @BotFather.

---

## Done?

After setup, you'll receive daily alerts at 9 AM IST with:
- Market regime summary
- Top 10 picks with scores
- Any instant alerts throughout the day

**Test now**:
```bash
python src/alerts.py --test-telegram
```

If successful, you're all set for the full platform! ✅
