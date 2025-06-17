"""
GPT utility module for generating tweets, threads, and longer text.
Logs errors to a centralized log file.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from .config import LOG_DIR

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
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content":
                        "You are a hedge fund manager. Provide sharp, insightful commentary "
                        "in up to ~240 characters, max 280, using 2–3 sentences. "
                        "No mid-sentence cuts and assume reader sees the headline."},
                    ),
                {"role": "user", "content": prompt},
            ],
            max_tokens=160,  # roughly 240 - 280 characters
            temperature=temperature,
        )
        core = response.choices[0].message.content.strip()
        # Enforce limit of 280 chars, trimming cleanly
        if len(core) > 280:
            core = core[:280].rsplit(" ", 1)[0]
        return core
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
