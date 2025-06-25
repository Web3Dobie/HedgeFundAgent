import os
import json
import logging
from collections import deque
import re
from datetime import datetime

logger = logging.getLogger(__name__)

THEME_STORE = os.path.join(os.path.dirname(__file__), "../data/recent_themes.json")
MAX_THEMES = 10
recent_themes = deque(maxlen=MAX_THEMES)
theme_day = None  # Track the day we loaded themes

def load_recent_themes():
    global recent_themes, theme_day
    today = datetime.utcnow().date().isoformat()
    theme_day = today

    if os.path.exists(THEME_STORE):
        try:
            with open(THEME_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("day") == today:
                    recent_themes_data = data.get("themes", [])
                    recent_themes = deque(recent_themes_data, maxlen=MAX_THEMES)
                    logger.info(f"Loaded recent themes: {list(recent_themes)}")
                else:
                    logger.info("New day detected, starting fresh theme tracker.")
        except Exception as e:
            logger.warning(f"Failed to load recent themes: {e}")

def save_recent_themes():
    try:
        with open(THEME_STORE, "w", encoding="utf-8") as f:
            json.dump({
                "day": theme_day,
                "themes": list(recent_themes)
            }, f)
            logger.info(f"Saved recent themes: {list(recent_themes)}")
    except Exception as e:
        logger.warning(f"Failed to save recent themes: {e}")

def extract_theme(headline: str) -> str:
    stopwords = {"the", "in", "of", "and", "to", "a", "after", "on", "for", "with"}
    words = re.findall(r'\b[A-Z][a-zA-Z]+\b', headline)
    if words:
        return words[0]
    tokens = [w for w in re.findall(r'\w+', headline.lower()) if w not in stopwords]
    return ' '.join(tokens[:2])

def is_duplicate_theme(new_theme: str) -> bool:
    for theme in recent_themes:
        if new_theme.lower() == theme.lower():
            logger.info(f"Theme '{new_theme}' matches recent theme '{theme}'")
            return True
    return False

def track_theme(theme: str):
    recent_themes.append(theme)
    save_recent_themes()
