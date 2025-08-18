import sys, io, logging
import os
import time
import traceback
from datetime import datetime, timezone
from functools import partial, wraps

import schedule
from dotenv import load_dotenv

from content.hedgefund_commentary import post_hedgefund_comment
from content.hedgefund_deep_dive import post_hedgefund_deep_dive
from content.briefings import run_briefing
from utils import fetch_and_score_headlines, rotate_logs
from utils.tg_notifier import send_telegram_message

load_dotenv()

# Using same naming convention as X-AI-Agent
BOT_ID = os.getenv("TG_BOT_TOKEN")

# Re-wrap stdout/stderr so they use UTF-8 instead of cp1252:
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stdout
)

def send_telegram_log(message: str, level: str = "INFO"):
    """Send formatted log message to Telegram"""
    emoji_map = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "WARNING": "⚠️",
        "ERROR": "❌",
        "START": "🚀",
        "COMPLETE": "🎯",
        "HEARTBEAT": "💓"
    }
    
    emoji = emoji_map.get(level, "📝")
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    try:
        send_telegram_message(f"{emoji} **{level}** | {timestamp}\n{message}")
    except Exception as e:
        logging.error(f"Failed to send Telegram log: {e}")

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

def telegram_job_wrapper(job_name: str):
    """Enhanced decorator combining Telegram logging with crash handling"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now()
            
            # Log job start
            send_telegram_log(f"Starting: `{job_name}`", "START")
            logging.info(f"🚀 Starting job: {job_name}")
            
            try:
                # Execute the job
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration = datetime.now() - start_time
                duration_str = str(duration).split('.')[0]  # Remove microseconds
                
                # Log successful completion
                send_telegram_log(
                    f"Completed: `{job_name}`\n⏱️ Duration: {duration_str}", 
                    "COMPLETE"
                )
                logging.info(f"✅ Completed job: {job_name} in {duration_str}")
                
                return result
                
            except Exception as e:
                # Calculate duration even for failed jobs
                duration = datetime.now() - start_time
                duration_str = str(duration).split('.')[0]
                
                # Log error with details to Telegram
                error_msg = f"Failed: `{job_name}`\n⏱️ Duration: {duration_str}\n❌ Error: {str(e)}"
                send_telegram_log(error_msg, "ERROR")
                
                # Send detailed crash alert (keeps existing functionality)
                detailed_error = f"Job '{job_name}' failed: {str(e)}\n{traceback.format_exc()}"
                send_crash_alert(detailed_error, "JOB FAILURE")
                
                # Also log full traceback locally
                logging.error(f"❌ Job failed: {job_name}")
                logging.error(f"Error: {str(e)}")
                logging.error(traceback.format_exc())
                
                # Don't re-raise to maintain existing behavior (let scheduler continue)
                
        return wrapper
    return decorator

print("🕒 HedgeFund Investor Scheduler is live. Waiting for scheduled posts…")
sys.stdout.flush()

# Send startup notification
send_telegram_log("HedgeFund Scheduler Started 💰\nAll scheduled jobs are now active", "SUCCESS")

# --- Schedule Jobs with Enhanced Telegram Logging ---

# Headlines ingestion with detailed tracking
schedule.every().hour.at(":30").do(
    telegram_job_wrapper("fetch_and_score_headlines")(fetch_and_score_headlines)
)

# --- Daily Hedge Fund Commentary Tweets ---
for hour in range(9, 21, 3):  # 9am, 12am, 3pm, 6pm, 9pm
    schedule.every().day.at(f"{hour:02d}:00").do(
        telegram_job_wrapper(f"hedgefund_comment_{hour:02d}h")(post_hedgefund_comment)
    )

# --- Weekday Briefings with Time-Specific Tracking ---
briefing_schedule = {
    "06:45": "morning",
    "13:10": "pre_market", 
    "16:00": "mid_day",
    "21:40": "after_market"
}

for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
    for time_str, briefing_type in briefing_schedule.items():
        job_name = f"{briefing_type}_briefing_{day}_{time_str.replace(':', '')}"
        getattr(schedule.every(), day).at(time_str).do(
            telegram_job_wrapper(job_name)(partial(run_briefing, briefing_type))
        )

# --- Daily Deep Dive Thread ---
schedule.every().day.at("22:00").do(
    telegram_job_wrapper("deep_dive_thread_22h")(post_hedgefund_deep_dive)
)

# --- Weekly Log Rotation ---
schedule.every().sunday.at("23:50").do(
    telegram_job_wrapper("weekly_log_rotation")(rotate_logs)
)

# --- Enhanced Run Loop with Heartbeat and Crash Detection ---
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
                next_job = schedule.next_run()
                next_job_str = next_job.strftime('%H:%M') if next_job else "None"
                
                heartbeat_msg = f"HedgeFund Scheduler Alive 💓\n📊 Jobs: {pending_jobs} active\n⏰ Next: {next_job_str}"
                send_telegram_log(heartbeat_msg, "HEARTBEAT")
                last_heartbeat = current_time
                
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            logging.info("⏹️ Scheduler shutdown requested")
            send_telegram_log("HedgeFund Scheduler Shutdown ⏹️\nManual stop requested", "WARNING")
            break
            
        except Exception as e:
            error_msg = f"Scheduler loop error: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            send_crash_alert(error_msg, "SCHEDULER LOOP ERROR")
            time.sleep(60)  # Wait before retrying
            
except Exception as fatal_error:
    fatal_msg = f"Fatal scheduler error: {str(fatal_error)}\n{traceback.format_exc()}"
    logging.critical(fatal_msg)
    send_crash_alert(fatal_msg, "FATAL ERROR")
    raise