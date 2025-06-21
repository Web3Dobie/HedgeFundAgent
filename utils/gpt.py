"""
GPT utility module for generating tweets, threads, and longer text.
Logs errors to a centralized log file and uses HTTP requests for API calls.
"""

import logging
import os
import requests
from dotenv import load_dotenv

from .config import LOG_DIR
from .stock_finder import get_relevant_tickers

from utils.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_DEPLOYMENT_ID,
    AZURE_API_VERSION,
    AZURE_RESOURCE_NAME,
)

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

# Base URL for Azure OpenAI requests
AZURE_OPENAI_BASE_URL = f"https://{AZURE_RESOURCE_NAME}.cognitiveservices.azure.com/openai/deployments/{AZURE_DEPLOYMENT_ID}/chat/completions?api-version={AZURE_API_VERSION}"


def generate_gpt_tweet(prompt: str, temperature: float = 0.7) -> str:
    """
    Generate commentary with room to expand: target ~240 chars, allow up to 280.
    Automatically adds relevant cashtags.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY,
        }
        payload = {
            "messages": [
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
            "temperature": temperature,
            "max_tokens": 160,
        }

        response = requests.post(AZURE_OPENAI_BASE_URL, headers=headers, json=payload)

        # Log and handle unsuccessful responses
        if response.status_code != 200:
            logging.error(
                f"Error generating GPT tweet: HTTP {response.status_code}, Response: {response.text}"
            )
            return ""

        result = response.json()["choices"][0]["message"]["content"].strip()

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
    Generate a multi-part thread on X (Twitter) using GPT.

    Each part should provide tweet-sized insights separated by the specified delimiter.
    Example use cases include macro analysis or stock commentary.

    Args:
        prompt (str): User's input topic or query.
        max_parts (int): Maximum number of thread parts (default: 5).
        delimiter (str): String used to separate different parts in the response (default: "---").
        max_tokens (int): Maximum tokens allowed in the GPT response (default: 1500).

    Returns:
        list[str]: List of tweet-sized strings forming the thread.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY,
        }
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a hedge fund investor. Write exactly {max_parts} tweet-length insights separated by '{delimiter}'.\n"
                        "Each part should deepen the analysis or add nuance to the macro or equity view. No numbering."
                    )
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.85,
            "max_tokens": max_tokens,
        }

        response = requests.post(AZURE_OPENAI_BASE_URL, headers=headers, json=payload)

        # Log and handle unsuccessful responses
        if response.status_code != 200:
            logging.error(
                f"Error generating GPT thread: HTTP {response.status_code}, Response: {response.text}"
            )
            return []

        raw = response.json()["choices"][0]["message"]["content"].strip()
        parts = raw.split(delimiter)

        # Handle alternative formatting if delimiter doesn't work
        if len(parts) < max_parts:
            parts = raw.split("\n\n")  # Attempt splitting by newlines

        # Ensure each part is stripped of extra spaces and limit to `max_parts`
        return [p.strip() for p in parts if p.strip()][:max_parts]

    except Exception as e:
        logging.error(f"Error generating GPT thread: {e}")
        return []


def generate_gpt_text(prompt: str, max_tokens: int = 1800, model: str = "gpt-4") -> str:
    """
    Generate longer-form text (e.g., Substack article or blog post) using GPT.

    Args:
        prompt (str): User's input topic or query.
        max_tokens (int): Maximum tokens allowed in the GPT response (default: 1800).
        model (str): Model to use for generation (default: "gpt-4").

    Returns:
        str: Generated long-form text.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY,
        }
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": max_tokens,
        }

        response = requests.post(AZURE_OPENAI_BASE_URL, headers=headers, json=payload)

        # Log and handle unsuccessful responses
        if response.status_code != 200:
            logging.error(
                f"Error generating GPT text: HTTP {response.status_code}, Response: {response.text}"
            )
            return ""

        return response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logging.error(f"Error generating GPT text: {e}")
        return ""
