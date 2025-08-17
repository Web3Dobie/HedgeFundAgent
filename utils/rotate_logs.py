"""
Rotate key CSVs and logs weekly by moving them into dated subfolders under BACKUP_DIR.
Handles rolling retention for scored headlines and weekly rotation for other logs.
"""

import os
import shutil
import csv
from datetime import datetime, timedelta
from datetime import timezone
cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=7)
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
            
            # Robust timestamp parsing with explicit ISO8601 handling
            try:
                # First try ISO8601 format (which includes 'T' separator)
                df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
                print(f"[TIMESTAMP] Successfully parsed ISO8601 timestamps in {src}")
            except ValueError as iso_error:
                print(f"[TIMESTAMP] ISO8601 parsing failed, trying mixed format: {iso_error}")
                try:
                    # Fallback to mixed format parsing
                    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
                    print(f"[TIMESTAMP] Successfully parsed mixed format timestamps in {src}")
                except Exception as mixed_error:
                    print(f"[ERROR] All timestamp parsing methods failed for {src}")
                    print(f"  - ISO8601 error: {iso_error}")
                    print(f"  - Mixed format error: {mixed_error}")
                    print(f"  - Sample timestamps: {df['timestamp'].head().tolist()}")
                    return
            
            # Ensure timestamps are timezone-aware (convert to UTC if naive)
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
                print(f"[TIMEZONE] Converted naive timestamps to UTC for {src}")
            
            # Split into recent and old data - ensure cutoff is timezone-aware
            from datetime import timezone
            cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=7)
            recent = df[df['timestamp'] > cutoff]
            old = df[df['timestamp'] <= cutoff]

            # Save old data to backup
            if not old.empty:
                # Convert timestamps back to ISO format for consistent storage
                old_copy = old.copy()
                old_copy['timestamp'] = old_copy['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
                old_copy.to_csv(dst, index=False)
                print(f"[ROLLING] Moved {len(old)} old records to {dst}")

            # Keep recent data in original file
            if not recent.empty:
                recent_copy = recent.copy()
                recent_copy['timestamp'] = recent_copy['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
                recent_copy.to_csv(src, index=False)
                print(f"[KEEP] Retained {len(recent)} recent records in {src}")
            else:
                # If no recent data, create empty file with headers
                if headers:
                    with open(src, "w", encoding="utf-8") as f:
                        if isinstance(headers, list):
                            f.write(",".join(headers) + "\n")
                        else:
                            f.write(headers + "\n")
                    print(f"[EMPTY] No recent records, created empty file with headers: {src}")
            return
            
        except Exception as e:
            print(f"[ERROR] Failed to process rolling retention for {src}: {e}")
            # Print more detailed error information for debugging
            print(f"  - Error type: {type(e).__name__}")
            if hasattr(e, 'args') and e.args:
                print(f"  - Error details: {e.args}")
            return

    # Standard file rotation (non-rolling)
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

    # Define standard headers for scored headlines CSVs
    headlines_headers = ["score", "headline", "url", "ticker", "summary", "timestamp", "used_in_hourly_commentary"]

    # Rolling retention for main scored headlines file
    rotate_file(
        os.path.join(DATA_DIR, "scored_headlines.csv"),
        headers=headlines_headers,
        rolling=True
    )

    # Rolling retention for category-specific scored headlines files
    rotate_file(
        os.path.join(DATA_DIR, "scored_headlines_equity.csv"),
        headers=headlines_headers,
        rolling=True
    )
    
    rotate_file(
        os.path.join(DATA_DIR, "scored_headlines_macro.csv"),
        headers=headlines_headers,
        rolling=True
    )
    
    rotate_file(
        os.path.join(DATA_DIR, "scored_headlines_political.csv"),
        headers=headlines_headers,
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