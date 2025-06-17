"""
GPT utility module for generating tweets, threads, and longer text.
Logs errors to a centralized log file.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from .config import LOG_DIR
from .stock_finder import get_relevant_tickers

# Load environment variables
load_dotenv()

# Configure logging
log_file = os.path.join(LOG_DIR, "gpt.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

client = OpenAI()

def generate_gpt_tweet(prompt: str, temperature: float = 0.7) -> str:
    """
    Generate commentary with room to expand: target ~240 chars, allow up to 280.
    Automatically adds relevant cashtags.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert hedge fund manager. Analyze the topic and return in format:\n"
                        "THEME|COMMENTARY\n\n"
                        "Requirements for commentary:\n"
                        "- Provide sharp, data-driven market analysis\n"
                        "- Include specific market implications\n"
                        "- Focus on actionable investment insights\n"
                        "- Target ~240 chars (max 280)\n"
                        "- Theme should be 1-3 key words\n"
                        "\nExample format:\n"
                        "HOMEBUILDERS|Housing starts plunge 15% to 3-year low as mortgage rates hit 7%. "
                        "Seeing inventory buildup and margin pressure for builders. "
                        "Watch for potential consolidation in smaller players."
                    )
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=160,
            temperature=temperature,
        )
        
        result = response.choices[0].message.content.strip()

        # Handle malformed responses
        if "|" not in result:
            logging.warning("Malformed GPT response, no theme separator found")
            return result[:280]
            
        theme, commentary = result.split("|", 1)
        commentary = commentary.strip()
        
        # Get relevant tickers
        tickers = get_relevant_tickers(theme.strip())
        
        # Start with commentary (allow full 280 chars)
        final_tweet = commentary
        
        # Trim commentary if over 280 (clean break at word boundary)
        if len(final_tweet) > 280:
            final_tweet = final_tweet[:280].rsplit(" ", 1)[0]
        
        # Add tickers separately (no length restriction)
        if tickers:
            final_tweet += "\n\n" + " ".join(tickers)
        
        # Add NFA disclaimer (always add, no length restriction)
        final_tweet += "\n\nThis is my opinion. Not financial advice."
        
        return final_tweet.strip()
        
    except Exception as e:
        logging.error(f"Error generating GPT tweet: {e}")
        return ""


def generate_gpt_thread(
    prompt: str, max_parts: int = 5, delimiter: str = "---", max_tokens: int = 1500
) -> list[str]:
    """
    Generate a multi-part thread for X via GPT.
    """
    try:
        system_prompt = (
            f"You are a hedge fund investor. Write exactly {max_parts} tweet-length insights separated by '{delimiter}'.\n"
            "Each part should deepen the analysis or add nuance to the macro or equity view. No numbering."
        )
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.85,
        )
        raw = response.choices[0].message.content.strip()
        parts = raw.split(delimiter)
        if len(parts) < max_parts:
            parts = raw.split("\n\n")
        return [p.strip() for p in parts if p.strip()][:max_parts]
    except Exception as e:
        logging.error(f"Error generating GPT thread: {e}")
        return []

def generate_gpt_text(prompt: str, max_tokens: int = 1800, model: str = "gpt-4") -> str:
    """
    Generate longer form text (e.g., Substack article) using GPT.
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generating GPT text: {e}")
        return ""
