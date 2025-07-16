import sys, io, logging
import os
import time
import traceback
from datetime import datetime, timezone
from functools import partial

import schedule
from dotenv import load_dotenv

from content.hedgefund_commentary import post_hedgefund_comment
from content.hedgefund_deep_dive import post_hedgefund_deep_dive
from content.briefings import run_briefing
from utils import fetch_and_score_headlines, rotate_logs
from utils.tg_notifier import send_telegram_message

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stdout
)

def send_crash_alert(error_details: str, error_type: str = "CRASH"):
    """Send detailed crash notification to Telegram"""
    hostname = os.uname().nodename if hasattr(os, 'uname') else 'Unknown'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    message = f"""
🚨 **HEDGEFUND SCHEDULER {error_type}** 🚨

**Time**: {timestamp}
**Server**: {hostname}
**Process**: HedgeFund Scheduler

**Error Details**:
```
{error_details}
```

**Action Required**: Check server and restart scheduler
    """.strip()
    
    try:
        send_telegram_message(message)
        logging.error(f"[ALERT SENT] {error_type} notification sent to Telegram")
    except Exception as e:
        logging.error(f"[ALERT FAILED] Could not send Telegram alert: {e}")

def safe_job_wrapper(func, job_name: str):
    """Wrapper to catch and alert on individual job failures"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Job '{job_name}' failed: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            send_crash_alert(error_msg, "JOB FAILURE")
            # Don't re-raise - let scheduler continue with other jobs
    return wrapper

print("🕒 Hedge Fund Investor Scheduler is live. Waiting for scheduled posts…")
sys.stdout.flush()

# Send startup notification
try:
    send_telegram_message("✅ **HedgeFund Scheduler Started**\n🕒 All scheduled jobs are now active")
except Exception:
    pass  # Don't fail startup if Telegram is down

# --- Schedule Jobs with Error Wrapping ---
schedule.every().hour.at(":30").do(
    safe_job_wrapper(fetch_and_score_headlines, "fetch_and_score_headlines")
)

# --- Daily Hedge Fund Tweets ---
for hour in range(9, 21, 3):  # 9am, 12am, 3pm, 6pm, 9pm
    schedule.every().day.at(f"{hour:02d}:00").do(
        safe_job_wrapper(post_hedgefund_comment, f"hedgefund_comment_{hour}")
    )

# --- Weekday Briefings ---
for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
    getattr(schedule.every(), day).at("06:45").do(
        safe_job_wrapper(partial(run_briefing, "morning"), f"morning_briefing_{day}")
    )
    getattr(schedule.every(), day).at("13:10").do(
        safe_job_wrapper(partial(run_briefing, "pre_market"), f"pre_market_briefing_{day}")
    )
    getattr(schedule.every(), day).at("16:00").do(
        safe_job_wrapper(partial(run_briefing, "mid_day"), f"mid_day_briefing_{day}")
    )
    getattr(schedule.every(), day).at("21:40").do(
        safe_job_wrapper(partial(run_briefing, "after_market"), f"after_market_briefing_{day}")
    )

# --- Daily Deep Dive Thread ---
schedule.every().day.at("22:00").do(
    safe_job_wrapper(post_hedgefund_deep_dive, "deep_dive_thread")
)

# --- Weekly Log Rotation ---
schedule.every().sunday.at("23:50").do(
    safe_job_wrapper(rotate_logs, "log_rotation")
)

# --- Enhanced Run Loop with Crash Detection ---
last_heartbeat = time.time()
heartbeat_interval = 3600  # Send heartbeat every hour

try:
    while True:
        try:
            schedule.run_pending()
            
            # Send periodic heartbeat to confirm scheduler is alive
            current_time = time.time()
            if current_time - last_heartbeat > heartbeat_interval:
                pending_jobs = len(schedule.get_jobs())
                send_telegram_message(f"💓 **Scheduler Heartbeat**\n⏰ {datetime.now().strftime('%H:%M')} - {pending_jobs} jobs scheduled")
                last_heartbeat = current_time
                
        except Exception as e:
            error_details = f"Scheduler loop error: {str(e)}\n{traceback.format_exc()}"
            send_crash_alert(error_details, "LOOP ERROR")
            logging.error(f"Error in scheduler loop: {e}")
            # Wait a bit before retrying
            time.sleep(60)
            
        time.sleep(30)
        
except KeyboardInterrupt:
    logging.info("Scheduler stopped by user (SIGINT)")
    try:
        send_telegram_message("⏹️ **HedgeFund Scheduler Stopped**\n👤 Manual shutdown via SIGINT")
    except Exception:
        pass
    sys.exit(0)
    
except Exception as e:
    # Critical crash - send alert and exit
    error_details = f"CRITICAL SCHEDULER CRASH: {str(e)}\n{traceback.format_exc()}"
    send_crash_alert(error_details, "CRITICAL CRASH")
    logging.critical(error_details)
    sys.exit(1)