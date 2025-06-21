"""
Rotate key CSVs and logs weekly by moving them into dated subfolders under BACKUP_DIR.
Handles rolling retention for scored headlines and weekly rotation for other logs.
"""

import os
import shutil
import csv
from datetime import datetime, timedelta
import pandas as pd

from .config import BACKUP_DIR, DATA_DIR, LOG_DIR

# Ensure backup directory exists
os.makedirs(BACKUP_DIR, exist_ok=True)

# List of log files to rotate weekly
LOG_FILES = [
    "gpt.log",
    "content.market_summary.log",
    "content.news_recap.log",
    "content.opinion_thread.log",
    "content.ta_poster.log",
    "utils.rss_fetch.log",
    "notion_logger.log",
    "x_post_http.log"
]

def rotate_file(src, headers=None, rolling=False):
    """
    Move the source file to BACKUP_DIR with a date suffix.
    For rolling retention, only moves records older than 7 days.
    Optionally recreate the file with headers.
    """
    if not os.path.exists(src):
        return

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    base = os.path.basename(src)
    name, ext = os.path.splitext(base)
    subdir = f"{name}_backup"
    dst_dir = os.path.join(BACKUP_DIR, subdir)
    os.makedirs(dst_dir, exist_ok=True)

    dst = os.path.join(dst_dir, f"{name}_{date_str}{ext}")

    if rolling and ext == '.csv':
        try:
            # Read CSV with pandas
            df = pd.read_csv(src)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Split into recent and old data
            cutoff = datetime.utcnow() - timedelta(days=7)
            recent = df[df['timestamp'] > cutoff]
            old = df[df['timestamp'] <= cutoff]

            # Save old data to backup
            if not old.empty:
                old.to_csv(dst, index=False)
                print(f"[ROLLING] Moved {len(old)} old records to {dst}")

            # Keep recent data in original file
            recent.to_csv(src, index=False)
            print(f"[KEEP] Retained {len(recent)} recent records in {src}")
            return
            
        except Exception as e:
            print(f"[ERROR] Failed to process rolling retention for {src}: {e}")
            return

    # Standard file rotation
    try:
        shutil.move(src, dst)
        print(f"[FOLDER] Moved {src} → {dst}")
    except Exception as e:
        print(f"[ERROR] Failed to move {src}: {e}")
        return

    # Recreate file with headers if needed
    if headers:
        try:
            with open(src, "w", encoding="utf-8") as f:
                if isinstance(headers, list):
                    f.write(",".join(headers) + "\n")
                else:
                    f.write(headers + "\n")
            print(f"[NEW] Recreated {src} with headers.")
        except Exception as e:
            print(f"[ALERT] Could not recreate {src}: {e}")

def clear_xrp_flag():
    """
    Clear the XRP flag file if it exists.
    Used to reset XRP tweet tracking between rotations.
    """
    flag_file = os.path.join(DATA_DIR, ".xrp_tweeted")
    if os.path.exists(flag_file):
        try:
            os.remove(flag_file)
            print("[FLAG] Cleared XRP tweet flag")
        except Exception as e:
            print(f"[ERROR] Failed to clear XRP flag: {e}")

def rotate_logs():
    """
    Perform weekly rotation of logs and rolling retention for headlines.
    """
    print("Starting log rotation...")

    # Rolling retention for scored headlines
    rotate_file(
        os.path.join(DATA_DIR, "scored_headlines.csv"),
        headers=["score", "headline", "url", "ticker", "timestamp"," used_in_hourly_commentary"],
        rolling=True
    )

    # Weekly rotation for tweet log
    rotate_file(
        os.path.join(DATA_DIR, "tweet_log.csv"),
        headers="tweet_id,timestamp,type,category,text,engagement_score"
    )

    # Rotate all log files
    for log_file in LOG_FILES:
        rotate_file(os.path.join(LOG_DIR, log_file))

    print("[OK] Log rotation complete.")

if __name__ == "__main__":
    rotate_logs()