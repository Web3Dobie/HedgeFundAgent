import os
import csv
import logging
from datetime import datetime, timezone
from .config import DATA_DIR

SCORED_FILE = os.path.join(DATA_DIR, "scored_headlines.csv")
logger = logging.getLogger(__name__)


def get_unused_headline_today_for_hourly():
    """
    Return highest-scoring headline from today that hasn't yet been used
    in hourly commentary tweets.
    """
    try:
        with open(SCORED_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        logger.warning("[ALERT] No scored headlines file found.")
        return None

    today = datetime.now(timezone.utc).date()
    candidates = []

    for r in rows:
        try:
            parsed = datetime.fromisoformat(r["timestamp"])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if (
            parsed.date() == today and
            r.get("used_in_hourly_commentary", "False").lower() != "true"
        ):
            candidates.append(r)

    if not candidates:
        logger.info("[HOURLY] No unused headline found for hourly commentary.")
        return None

    return max(candidates, key=lambda r: float(r["score"]))


def mark_headline_used_in_hourly_commentary(headline_text, reason="True"):
    """
    Mark the given headline as used for hourly commentary in the CSV,
    with a reason ("True" [posted], "filtered", "empty", etc.).
    """
    temp_file = os.path.join(DATA_DIR, "tmp_scored_headlines.csv")
    try:
        with open(SCORED_FILE, "r", encoding="utf-8") as fin, \
             open(temp_file, "w", encoding="utf-8", newline="") as fout:

            reader = csv.DictReader(fin)
            fieldnames = reader.fieldnames
            if "used_in_hourly_commentary" not in fieldnames:
                fieldnames.append("used_in_hourly_commentary")
            if "filter_reason" not in fieldnames:
                fieldnames.append("filter_reason")

            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                if row["headline"] == headline_text:
                    row["used_in_hourly_commentary"] = reason
                    # Only set filter_reason if NOT "True"
                    row["filter_reason"] = "" if reason == "True" else reason
                else:
                    # Ensure the column is present, even if empty
                    row.setdefault("used_in_hourly_commentary", "False")
                    row.setdefault("filter_reason", "")
                writer.writerow(row)

        os.replace(temp_file, SCORED_FILE)
        logger.info(f"[TRACKED] Marked headline as used: {headline_text[:80]} ({reason})")
        logger.info(f"[CHECK] File size after overwrite: {os.path.getsize(SCORED_FILE)} bytes")

    except Exception as e:
        logger.error(f"[ERROR] Failed to mark headline as used: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


