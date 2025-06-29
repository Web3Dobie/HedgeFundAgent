import sys, io, logging
import os
import time
from datetime import datetime, timezone

import schedule
from dotenv import load_dotenv

from content.hedgefund_commentary import post_hedgefund_comment
from content.hedgefund_deep_dive import post_hedgefund_deep_dive
from content.briefings import run_morning_briefing
from utils import fetch_and_score_headlines, rotate_logs

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stdout
)

print("🕒 Hedge Fund Investor Scheduler is live. Waiting for scheduled posts…")
sys.stdout.flush()

# --- Ingest Headlines Hourly ---
schedule.every().hour.at(":30").do(fetch_and_score_headlines)

# --- Daily Hedge Fund Tweets ---
for hour in range(9, 21, 2):  # 9am, 11am, 1pm, 3pm, 5pm, 7pm
    schedule.every().day.at(f"{hour:02d}:00").do(post_hedgefund_comment)

# --- Weekday Morning Briefing ---
for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
    getattr(schedule.every(), day).at("06:00").do(run_morning_briefing)

# --- Daily Deep Dive Thread ---
schedule.every().day.at("22:00").do(post_hedgefund_deep_dive)

# --- Weekly Log Rotation ---
schedule.every().sunday.at("23:50").do(rotate_logs)

# --- Run Loop ---
try:
    while True:
        schedule.run_pending()
        time.sleep(30)
except KeyboardInterrupt:
    logger.info("Scheduler stopped by user (SIGINT)")
    sys.exit(0)