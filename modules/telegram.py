"""
Telegram notification helper.
Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to enable.
"""
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# Load .env from the app root directory (works regardless of cwd)
_ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(_ENV_PATH)

_IST       = timezone(timedelta(hours=5, minutes=30))
_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')
print(f'[TELEGRAM] Configured: BOT={bool(_BOT_TOKEN)} CHAT={bool(_CHAT_ID)}')


def send_message(text: str, parse_mode: str = 'HTML') -> bool:
    """Send a plain message. Returns True on success."""
    if not _BOT_TOKEN or not _CHAT_ID:
        print(f'[TELEGRAM] Not configured — message not sent: {text[:80]}')
        return False
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage',
            json={'chat_id': _CHAT_ID, 'text': text, 'parse_mode': parse_mode},
            timeout=8,
        )
        if not r.ok:
            print(f'[TELEGRAM] API error {r.status_code}: {r.text[:120]}')
        return r.ok
    except Exception as e:
        print(f'[TELEGRAM] send failed: {e}')
        return False


def send_sr_alert(index_id: str, level: float, level_type: str,
                  ltp: float, distance_pct: float) -> bool:
    """Send a formatted S/R proximity alert."""
    icon      = '🛡️' if level_type == 'support' else '🚧'
    direction = 'above' if ltp > level else 'below'
    now_str   = datetime.now(_IST).strftime('%H:%M IST')
    text = (
        f'{icon} <b>S/R Alert — {index_id}</b>\n\n'
        f'<b>{level_type.capitalize()}:</b> ₹{level:,.2f}\n'
        f'<b>LTP:</b> ₹{ltp:,.2f} ({direction})\n'
        f'<b>Distance:</b> {distance_pct:.3f}%\n'
        f'<b>Time:</b> {now_str}'
    )
    return send_message(text)
