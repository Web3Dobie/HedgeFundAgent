import os
import requests

TOKEN   = os.getenv('TG_BOT_TOKEN')
CHAT_ID = os.getenv('TG_CHAT_ID')

def send_telegram_message(text: str):
    """
    Send a markdown-formatted message to your TG chat.
    """
    url     = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    resp    = requests.post(url, data=payload)
    resp.raise_for_status()
