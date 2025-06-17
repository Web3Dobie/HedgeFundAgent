import logging
from .tg_notifier import send_telegram_message

class TelegramHandler(logging.Handler):
    """A logging handler that sends INFO+ records to Telegram."""

    def emit(self, record):
        try:
            # Only forward INFO and above (this will catch your [OK], WARN and ERROR logs)
            if record.levelno >= logging.INFO:
                msg = self.format(record)
                # Prefix with an emoji based on level
                prefix = {
                    logging.INFO:    "✅",
                    logging.WARNING: "⚠️",
                    logging.ERROR:   "❌",
                    logging.CRITICAL:"💥",
                }.get(record.levelno, "")
                send_telegram_message(f"{prefix} *Log {record.levelname}*\n{msg}")
        except Exception:
            # Don’t let Telegram failures crash your app
            pass
