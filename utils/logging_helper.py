# utils/logging_helper.py

import logging
import os

from utils.config import LOG_DIR    # or however you import your LOG_DIR constant

def get_module_logger(name: str = None) -> logging.Logger:
    """
    Return a logger which writes to LOG_DIR/<module_name>.log at INFO level.
    If `name` is None, uses the calling module's __name__.
    """
    # Determine logger/name
    module_name = name or logging.root.findCaller()[0].rsplit(os.sep, 1)[-1].rsplit(".", 1)[0]
    # (Alternatively, callers can explicitly pass __name__.)

    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)

    # Ensure the log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # Build the absolute path to this modules log file
    log_file = os.path.join(LOG_DIR, f"{module_name}.log")

    # Check whether a FileHandler for this exact file already exists
    handler_exists = any(
        isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
        for h in logger.handlers
    )
    if not handler_exists:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(fh)

    return logger
