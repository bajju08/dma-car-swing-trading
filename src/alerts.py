"""
Alerts Module – Send notifications via Telegram and Email.

Supports:
- Daily recommendations summary
- Instant alerts (target hit, bear run signal)
- Trade journal updates
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from datetime import datetime
from typing import List, Dict, Optional
from .utils import load_config, logger, format_currency, format_percent

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for sending messages."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text: str, parse_mode: str = "MarkdownV2") -> bool:
        """Send a message to chat."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, data=payload, timeout=10)
            if resp.status_code == 200:
                logger.debug(f"Telegram message sent: {text[:50]}...")
                return True
            else:
                logger.error(f"Telegram error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_document(self, file_path: str, caption: str = None) -> bool:
        """Send a file (like JSON recommendations)."""
        url = f"{self.base_url}/sendDocument"
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': self.chat_id, 'caption': caption}
            try:
                resp = requests.post(url, files=files, data=data, timeout=30)
                return resp.status_code == 200
            except Exception as e:
                logger.error(f"Telegram document send failed: {e}")
                return False


class EmailSender:
    """Send emails via SMTP."""

    def __init__(self, smtp_server: str, smtp_port: int, sender_email: str, sender_password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send_email(self, to_emails: List[str], subject: str, html_body: str, text_body: str = None) -> bool:
        """Send an email."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = ', '.join(to_emails)

        # Text part
        if text_body:
            part1 = MIMEText(text_body, 'plain')
            msg.attach(part1)

        # HTML part
        part2 = MIMEText(html_body, 'html')
        msg.attach(part2)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            logger.info(f"Email sent to {to_emails}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_daily_telegram_message(recs: dict) -> str:
    """Format daily recommendations as a Telegram message (MarkdownV2)."""
    date_str = recs['date']
    regime = recs['market_regime']['classification']
    nifty_status = recs['market_regime']['nifty_status']
    bull_pct = recs['market_regime']['bull_percentage'] * 100

    # Use raw string to avoid escape issues
    message = rf"""📊 *DMA\-DMA\+CAR Daily Picks* \- {date_str}

🏛 *Market Regime:* {regime}
   Nifty: {nifty_status} \| Stocks Bull: {bull_pct:.1f}%
   Position Size: {recs['market_regime']['position_multiplier']:.0%}

🚀 *Top {min(10, len(recs['top_picks']))}:*
"""

    for i, pick in enumerate(recs['top_picks'][:10], 1):
        symbol = pick['symbol']
        signal = pick['master_signal']
        score = pick['enhanced_score']
        speed = pick['speed_score']
        cmp = pick['cmp']
        target = cmp * 1.0628
        dma = pick['dma_status']
        car = pick['car_signal']

        # Escape special chars for MarkdownV2
        symbol = escape_markdown_v2(symbol)
        signal = escape_markdown_v2(signal)
        dma = escape_markdown_v2(dma)
        car = escape_markdown_v2(car)

        message += rf"""
{i}\. {symbol}  *{signal}*
   Score: {score}/15 \| Speed: {speed}/10
   CMP: ₹{cmp:,.0f} → Target: ₹{target:,.0f} \(6\.28\%\) ✅
   DMA: {dma} \| CAR: {car}
"""

    message += rf"""
📈 Total Qualified: {recs['total_qualified']} stocks

_Daily scan completed at {datetime.now().strftime('%H:%M')} IST_ ✅
"""
    return message


def send_daily_report(recommendations: dict, config: dict):
    """Send daily recommendations via Telegram and Email."""
    # Telegram
    tg_cfg = config.get('telegram', {})
    if tg_cfg.get('bot_token') and tg_cfg.get('chat_id'):
        bot = TelegramBot(tg_cfg['bot_token'], tg_cfg['chat_id'])
        msg = format_daily_telegram_message(recommendations)
        sent = bot.send_message(msg)
        if sent:
            logger.info("Telegram daily report sent")
        else:
            logger.error("Failed to send Telegram report")
    else:
        logger.warning("Telegram not configured (missing bot_token or chat_id)")

    # Email
    email_cfg = config.get('email', {})
    if email_cfg.get('sender_email') and email_cfg.get('sender_password') and email_cfg.get('recipients'):
        sender = EmailSender(
            email_cfg['smtp_server'],
            email_cfg['smtp_port'],
            email_cfg['sender_email'],
            email_cfg['sender_password']
        )
        html_body = f"""<html><body>
<h1>DMA-DMA+CAR Daily Picks - {recommendations['date']}</h1>
<p><strong>Regime:</strong> {recommendations['market_regime']['classification']}</p>
<p><strong>Nifty:</strong> {recommendations['market_regime']['nifty_status']} | <strong>Bull %:</strong> {recommendations['market_regime']['bull_percentage']*100:.1f}%</p>
<h2>Top Picks</h2>
<table border="1" cellpadding="5">
<tr><th>#</th><th>Stock</th><th>Signal</th><th>Score</th><th>CMP</th><th>Target</th></tr>
"""
        for i, pick in enumerate(recommendations['top_picks'][:15], 1):
            html_body += f"""<tr>
<td>{i}</td>
<td>{pick['symbol']}</td>
<td>{pick['master_signal']}</td>
<td>{pick['enhanced_score']}/15</td>
<td>₹{pick['cmp']:,.0f}</td>
<td>₹{pick['cmp']*1.0628:,.0f}</td>
</tr>"""
        html_body += "</table></body></html>"

        text_body = f"DMA-DMA+CAR Daily Picks - {recommendations['date']}\n\n"
        for i, pick in enumerate(recommendations['top_picks'][:15], 1):
            text_body += f"{i}. {pick['symbol']} - {pick['master_signal']} (Score: {pick['enhanced_score']}) CMP: {pick['cmp']} Target: {pick['cmp']*1.0628}\n"

        sender.send_email(email_cfg['recipients'], f"DMA-DMA Picks {recommendations['date']}", html_body, text_body)
    else:
        logger.warning("Email not configured")


def send_alert_target_hit(stock: str, current_price: float, target: float):
    """Send instant alert when target is hit."""
    config = load_config()
    tg_cfg = config.get('telegram', {})
    if tg_cfg.get('bot_token') and tg_cfg.get('chat_id'):
        bot = TelegramBot(tg_cfg['bot_token'], tg_cfg['chat_id'])
        msg = rf"""🎯 *TARGET HIT* ✅

{stock} has reached target\!
*Current:* ₹{current_price:,.0f}
*Target:* ₹{target:,.0f} \(6\.28\%\)

Book profit now!"""
        bot.send_message(msg)


def send_alert_bear_run(stock: str, reason: str):
    """Send alert when stock turns Bear Run (exit signal)."""
    config = load_config()
    tg_cfg = config.get('telegram', {})
    if tg_cfg.get('bot_token') and tg_cfg.get('chat_id'):
        bot = TelegramBot(tg_cfg['bot_token'], tg_cfg['chat_id'])
        msg = rf"""⚠️ *BEAR RUN ALERT* \- EXIT

{stock} has entered {reason}
\- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \-
Exit immediately to protect capital\!
Review position and book loss if needed\."""
        bot.send_message(msg)


def test_alerts():
    """Test alert functionality."""
    config = load_config()

    print("Testing Telegram alert...")
    try:
        send_daily_report({
            'date': datetime.now().date().isoformat(),
            'market_regime': {'classification': 'FULL_BULL', 'nifty_status': 'In Bull Run', 'bull_percentage': 0.25, 'position_multiplier': 1.0},
            'top_picks': [],
            'total_qualified': 0,
            'total_scan': 500
        }, config)
        print("✅ Telegram test sent (if configured)")
    except Exception as e:
        print(f"❌ Telegram test failed: {e}")

    print("Testing Email alert...")
    # Email test would require valid SMTP config; skip for now

if __name__ == "__main__":
    test_alerts()
