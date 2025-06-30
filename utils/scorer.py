"""
GPT-based scoring for hedge fund investor headlines.
Logs scores to category-specific CSVs with trend boosting.
"""
import csv
import logging
import os
from datetime import datetime

from .config import DATA_DIR, LOG_DIR
from .gpt import generate_gpt_text
from .text_utils import classify_headline_topic
from .article_summarizer import summarize_url

# Logging setup
log_file = os.path.join(LOG_DIR, "scorer.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

CATEGORY_THRESHOLDS = {
    "equity": 6,
    "macro": 8,
    "political": 7,
}

def score_headlines(items: list[dict]) -> list[dict]:
    logging.info("Scoring headlines with trend detection and category routing...")
    scored_items = []
    failed_count = 0

    # Step 1: Score each headline individually
    for item in items:
        item.setdefault("score", 1)
        item.setdefault("url", "")
        item.setdefault("timestamp", datetime.utcnow().isoformat())
        item["category"] = classify_headline_topic(item.get("headline", ""))
        item["ticker"] = item["category"]

        summary = item.get("summary", "").strip()
        prompt = (
            "As a hedge fund analyst, rate this story's market impact from 1-10.\n\n"
            f"Headline:\n{item['headline']}\n\n"
            f"Summary:\n{summary if summary else '[No summary available]'}\n\n"
            "Score based on:\n"
            "- Immediate price action potential\n"
            "- Broader economic/policy implications\n"
            "- Sector-wide or geopolitical relevance\n"
            "- Unusual or market-moving information\n\n"
            "Score 8-10 for headlines with significant, multi-asset, or urgent impact.\n"
            "Return only the number."
        )
        raw = generate_gpt_text(prompt, max_tokens=10)

        if not raw or raw.strip() == "":
            logging.error(f"GPT returned empty for: {item['headline']}")
            item["score"] = 1
            failed_count += 1
        else:
            try:
                item["score"] = parse_score(raw)
                logging.info(f"Scored: {item['headline']} | {item['score']}")
            except Exception as e:
                logging.error(f"Score parse failed: {item['headline']} | Error: {e}")
                item["score"] = 1
                failed_count += 1

        scored_items.append(item)

    logging.info(f"Total scored: {len(scored_items)} | Failures: {failed_count}")

    # Step 2: Enhanced trend detection
    batch = "\n".join(f"- {i['headline']}" for i in scored_items)
    trend_prompt = (
        "From these headlines, identify the 3 most important *new or still-evolving* market stories.\n"
        "Avoid stale or already-priced-in themes unless there are major updates.\n"
        "Look for:\n"
        "- Policy shifts with fresh implications\n"
        "- Evolving geopolitical risk (not old flare-ups)\n"
        "- Surprising economic data\n"
        "- Major earnings, downgrades, upgrades\n"
        "- Cross-asset volatility triggers\n\n"
        f"{batch}\n\n"
        "Reply with exact headlines, one per line."
    )
    hot_lines = generate_gpt_text(trend_prompt, max_tokens=200).splitlines()
    hot_set = set(h.strip() for h in hot_lines)

    # Step 3: Apply trend boost and write to category CSV if above category threshold
    results = []
    for item in scored_items:
        headline = item["headline"]
        if headline in hot_set:
            item["score"] = min(10, item["score"] + 3)
            logging.info(f"Trend boost: {headline} | New score: {item['score']}")

        category = item["category"]
        threshold = CATEGORY_THRESHOLDS.get(category, 8)

        if item["score"] >= threshold:
            if item.get("url") and not item.get("summary"):
                try:
                    item["summary"] = summarize_url(item["url"])
                except Exception as e:
                    logging.warning(f"Summary fetch failed for {item['url']}: {e}")
                    item["summary"] = ""
            else:
                item.setdefault("summary", "")

            _append_to_category_csv(item)
            results.append(item)

    return results

def parse_score(raw_response: str) -> int:
    try:
        score = float(raw_response.strip())
        return min(10, max(1, int(round(score))))
    except ValueError:
        logging.error(f"Failed to parse score: '{raw_response}'")
        return 1

def _append_to_category_csv(record: dict):
    category = record.get("category", "macro")
    filepath = os.path.join(DATA_DIR, f"scored_headlines_{category}.csv")
    header = ["score", "headline", "url", "ticker", "summary", "timestamp", "used_in_hourly_commentary"]
    write_header = not os.path.exists(filepath)

    record.setdefault("used_in_hourly_commentary", "False")
    record.setdefault("summary", "")

    try:
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if write_header:
                writer.writeheader()
            writer.writerow(record)
    except Exception as e:
        logging.error(f"Write failed for {filepath}: {e}")
        raise

def write_headlines(records: list[dict]):
    for rec in records:
        rec.setdefault("url", "")
        rec.setdefault("ticker", classify_headline_topic(rec.get("headline", "")))
        rec.setdefault("timestamp", datetime.utcnow().isoformat())
        _append_to_category_csv(rec)
