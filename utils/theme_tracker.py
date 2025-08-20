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
    
    # Always try to load existing themes first
    if os.path.exists(THEME_STORE):
        try:
            with open(THEME_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
                stored_day = data.get("day")
                
                # If it's the same day, load the existing themes
                if stored_day == today:
                    recent_themes_data = data.get("themes", [])
                    recent_themes = deque(recent_themes_data, maxlen=MAX_THEMES)
                    theme_day = today
                    logger.info(f"✅ Loaded {len(recent_themes)} recent themes for today: {list(recent_themes)}")
                    return
                # If it's a new day, clear themes but keep the file structure
                elif stored_day is not None and stored_day != today:
                    logger.info(f"📅 New day detected ({stored_day} → {today}), starting fresh theme tracker.")
                    recent_themes.clear()
                    theme_day = today
                    save_recent_themes()  # Save empty themes for new day
                    return
                # If day is null or corrupted, fix it
                else:
                    logger.warning(f"⚠️ Invalid day in themes file ({stored_day}), fixing...")
                    theme_day = today
                    # Keep existing themes but fix the day
                    recent_themes_data = data.get("themes", [])
                    recent_themes = deque(recent_themes_data, maxlen=MAX_THEMES)
                    save_recent_themes()  # Fix the file
                    logger.info(f"✅ Fixed themes file and loaded {len(recent_themes)} themes: {list(recent_themes)}")
                    return
                    
        except Exception as e:
            logger.warning(f"⚠️ Failed to load recent themes: {e}")
    
    # If file doesn't exist or failed to load, create fresh
    logger.info("📝 Creating fresh theme tracker for today")
    recent_themes.clear()
    theme_day = today
    save_recent_themes()

def save_recent_themes():
    """Save themes with proper error handling and validation"""
    global theme_day
    
    # Ensure we have a valid day
    if theme_day is None:
        theme_day = datetime.utcnow().date().isoformat()
        
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(THEME_STORE), exist_ok=True)
        
        with open(THEME_STORE, "w", encoding="utf-8") as f:
            json.dump({
                "day": theme_day,
                "themes": list(recent_themes)
            }, f, indent=2)
        logger.info(f"💾 Saved {len(recent_themes)} themes for {theme_day}: {list(recent_themes)}")
    except Exception as e:
        logger.error(f"❌ Failed to save recent themes: {e}")

def extract_theme(headline: str) -> str:
    """Extract theme from headline with better logic"""
    stopwords = {"the", "in", "of", "and", "to", "a", "after", "on", "for", "with", "is", "are", "will", "has", "have"}
    
    # First try to find capitalized words (proper nouns, companies, etc.)
    words = re.findall(r'\b[A-Z][a-zA-Z]+\b', headline)
    if words:
        # Filter out common words that might be capitalized
        filtered_words = [w for w in words if w.lower() not in stopwords and len(w) > 2]
        if filtered_words:
            return filtered_words[0]
    
    # Fallback to first significant words
    tokens = [w for w in re.findall(r'\w+', headline.lower()) if w not in stopwords and len(w) > 2]
    return ' '.join(tokens[:2]) if tokens else "market"

def is_duplicate_theme(new_theme: str) -> bool:
    """Check if theme is duplicate with improved matching"""
    if not new_theme:
        return True
        
    new_theme_lower = new_theme.lower()
    
    for existing_theme in recent_themes:
        existing_lower = existing_theme.lower()
        
        # Exact match
        if new_theme_lower == existing_lower:
            logger.info(f"🔄 Exact duplicate theme: '{new_theme}' == '{existing_theme}'")
            return True
            
        # Partial match (if one contains the other)
        if len(new_theme_lower) > 3 and len(existing_lower) > 3:
            if new_theme_lower in existing_lower or existing_lower in new_theme_lower:
                logger.info(f"🔄 Partial duplicate theme: '{new_theme}' ≈ '{existing_theme}'")
                return True
    
    return False

def track_theme(theme: str):
    """Track a new theme with validation"""
    if not theme:
        logger.warning("⚠️ Attempted to track empty theme")
        return
        
    # Force reload themes to ensure we have latest state
    load_recent_themes()
    
    recent_themes.append(theme)
    save_recent_themes()
    logger.info(f"📝 Tracked new theme: '{theme}' (total: {len(recent_themes)})")

def get_recent_themes_summary() -> dict:
    """Get summary of current theme state for debugging"""
    return {
        "day": theme_day,
        "theme_count": len(recent_themes),
        "themes": list(recent_themes),
        "file_exists": os.path.exists(THEME_STORE)
    }

# Auto-load themes when module is imported
load_recent_themes()