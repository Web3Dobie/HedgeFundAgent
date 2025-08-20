import sys, io, logging
import os
import time
import traceback
import threading
from datetime import datetime, timezone
from functools import partial, wraps

import schedule
from dotenv import load_dotenv

from content.hedgefund_commentary import post_hedgefund_comment
from content.hedgefund_deep_dive import post_hedgefund_deep_dive
from content.briefings import run_briefing
from utils import fetch_and_score_headlines, rotate_logs
from utils.tg_notifier import send_telegram_message

# NEW IMPORTS for HedgeFund News Integration
from hedgefund_news_bridge import generate_hedgefund_news_for_website
from hedgefund_http_server import start_hedgefund_news_server

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

# NEW FUNCTION: HTTP Server Background Thread
def start_hedgefund_news_server_in_background():
    """Start the HedgeFund news HTTP server in a background thread"""
    try:
        start_hedgefund_news_server(port=3002)
    except Exception as e:
        send_telegram_log(f"HedgeFund news HTTP server failed to start: {e}", "ERROR")
        send_crash_alert(f"HTTP server startup failed: {str(e)}\n{traceback.format_exc()}", "SERVER STARTUP ERROR")

# NEW FUNCTION: Market Hours Check for Optional Frequent Updates
def is_market_hours():
    """Check if current time is during US market hours (9:30 AM - 4:00 PM ET)"""
    try:
        import pytz
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        # Check if it's a weekday (Monday=0, Sunday=6)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check if it's during market hours
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= now <= market_close
    except ImportError:
        # If pytz not available, default to simple time check
        now = datetime.now()
        # Assume EST/EDT and weekday
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 AM ET = 2:30 PM UTC approx
        market_close = now.replace(hour=21, minute=0, second=0, microsecond=0)   # 4:00 PM ET = 9:00 PM UTC approx
        return market_open <= now <= market_close

# NEW FUNCTION: Market Hours News Updates
def hedgefund_news_market_hours():
    """Generate hedge fund news if during market hours"""
    if is_market_hours():
        generate_hedgefund_news_for_website()
        logging.info("📊 Market hours hedge fund news update completed")
    else:
        logging.info("⏰ Outside market hours - skipping frequent hedge fund news update")

print("🕒 HedgeFund Investor Scheduler is live. Waiting for scheduled posts…")
sys.stdout.flush()

# NEW: Start HTTP server in background thread
print("🌐 Starting HedgeFund news HTTP server...")
hedgefund_http_thread = threading.Thread(target=start_hedgefund_news_server_in_background, daemon=True)
hedgefund_http_thread.start()

# Add a small delay to let the server start
time.sleep(3)

# Send startup notification
send_telegram_log("HedgeFund Scheduler Started 💰\nAll scheduled jobs are now active\n🌐 HTTP server running on port 3002", "SUCCESS")

# --- Schedule Jobs with Enhanced Telegram Logging ---

# Headlines ingestion with detailed tracking
schedule.every().hour.at(":30").do(
    telegram_job_wrapper("fetch_and_score_headlines")(fetch_and_score_headlines)
)

# NEW: HedgeFund News Website Generation
schedule.every().hour.at(":25").do(
    telegram_job_wrapper("hedgefund_news_website")(generate_hedgefund_news_for_website)
)

# NEW: Optional - More frequent updates during market hours (every 30 minutes)
# Uncomment the next 3 lines if you want more frequent updates during trading hours
# schedule.every(30).minutes.do(
#     telegram_job_wrapper("hedgefund_news_market_hours")(hedgefund_news_market_hours)
# )

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
                
                # NEW: Include HTTP server status in heartbeat
                heartbeat_msg = f"HedgeFund Scheduler Alive 💓\n📊 Jobs: {pending_jobs} active\n⏰ Next: {next_job_str}\n🌐 HTTP: Port 3002 active"
                send_telegram_log(heartbeat_msg, "HEARTBEAT")
                last_heartbeat = current_time
                
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            logging.info("⏹️ Scheduler shutdown requested")
            send_telegram_log("HedgeFund Scheduler Shutdown ⏹️\nManual stop requested\n🌐 HTTP server will stop", "WARNING")
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

# NEW: Cleanup message when scheduler stops (if we reach here)
finally:
    send_telegram_log("HedgeFund Scheduler Stopped 🛑\nAll services have been terminated", "WARNING")