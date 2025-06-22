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

def construct_azure_openai_url(deployment_id: str) -> str:
    """
    Constructs the complete Azure OpenAI URL based on deployment ID.
    :param deployment_id: Deployment ID as defined in Azure portal.
    :return: Fully constructed endpoint URL.
    """
    return f"https://{AZURE_RESOURCE_NAME}.cognitiveservices.azure.com/openai/deployments/{deployment_id}/chat/completions?api-version={AZURE_API_VERSION}"

def make_gpt_request(payload: dict, deployment_id: str) -> dict:
    """
    Sends a request to Azure OpenAI and returns the response.
    :param payload: Request payload for generating text.
    :param deployment_id: Deployment ID for the GPT model.
    :return: Response JSON or empty dictionary in case of error.
    """
    url = construct_azure_openai_url(deployment_id)
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY,
    }

    try:    
        response = requests.post(url, headers=headers, json=payload)

        # Log and handle unsuccessful responses
        if response.status_code != 200:
            return reponse.json()

        logging.error(
            f"Failed GPT request: HTTP {response.status_code}, Response: {response.text}"
        )
        return {}
    Except Exception as e:
        logging.error(f"Exception during GPT request: {e}")
        return {}


def generate_gpt_tweet(prompt: str, temperature: float = 0.7) -> str:
    """
    Generate commentary with room to expand: target ~240 chars, allow up to 280.
    Automatically adds relevant cashtags.
    """
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
        "top_p": 1.0,
    }

    try:
        response = make_gpt_request(payload, AZURE_DEPLOYMENT_ID)
        result = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if not result or "|" not in result:
            logging.warning("Malformed GPT response, no theme separator found")
            return result[:280]

        theme, commentary = map(str.strip, result.split("|", 1))
        tickers = get_relevant_tickers(theme)

        #create final tweet
        final_tweet = commentary[:280].rsplit(" ", 1)[0] if len(commentary) > 280 else commentary
        if tickers:
            final_tweet += "\n\n" + " ".join(tickers)
        final_tweet += "\n\nThis is my opinion. Not financial advice."

        return final_tweet.strip()

    except Exception as e:
        logging.error(f"Error generating GPT tweet: {e}")
        return ""

        # Log and handle unsuccessful responses
        if response.status_code != 200:
            logging.error(
                f"Error generating GPT tweet: HTTP {response.status_code}, Response: {response.text}"
            )
            return ""

def generate_gpt_thread(prompt: str, max_parts: int = 5, delimiter: str = "---", max_tokens: int = 1500) -> list[str]:
    """
    Generate a multi-part Twitter thread using GPT with numbered parts and disclaimer at the end of the last part.

    Args:
        prompt (str): User's input topic or query.
        max_parts (int): Maximum number of thread parts (default: 5).
        delimiter (str): String used to separate different parts in the response (default: "---").
        max_tokens (int): Maximum tokens allowed in the GPT response (default: 1500).

    Returns:
        list[str]: List of tweet-sized strings forming the thread.
    """
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are a hedge fund investor. Write exactly {max_parts} tweet-length insights separated by '{delimiter}'.\n"
                    "Each part should deepen the analysis or add nuance to the macro, political or equity view. No numbering."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.85,
        "max_tokens": max_tokens,
        "top_p": 1.0,
    }

    try:
        response = make_gpt_request(payload, AZURE_DEPLOYMENT_ID)
        raw_content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        parts = raw_content.split(delimiter) if delimiter in raw_content else raw_content.split("\n\n")

        #Process and format each part
        formatted_parts = []
        for i, part in enumerate(parts[:max_parts], start=1):
            part = part.strip()
            if not part:
                continue
            # Add numbering and thread symbol to each part
            formatted_part = f"{part} ↩\n\nPart {i}/{max_parts}"

            # Add disclaimer to the last part
            if i == max_parts:
                formatted_part += "\n\nThis is my opinion. Not financial advice."

            formatted_parts.append(formatted_part)

       return formatted_parts

    except Exception as e:
        logging.error(f"Error generating GPT thread: {e}")
        return []


def analyze_market_moves(news_data: dict, deployment_name: str = AZURE_DEPLOYMENT_ID) -> dict:
    """
    Uses GPT via Azure OpenAI to analyze market movements based on news headlines.
    :param news_data: Dictionary with gainers and losers news articles.
    :param deployment_name: Deployment name for Azure OpenAI.
    :return: Dictionary with GPT-generated insights.
    """
    insights = {}

    for category, news_dict in news_data.items():
        insights[category] = {}
        for ticker, articles in news_dict.items():
            headlines = [article["headline"] for article in articles]
            prompt = f"Analyze the following news for {ticker}:\n" + "\n".join(headlines)
            insights[category][ticker] = generate_gpt_text(prompt, deployment_name)

    return insights



def generate_gpt_text(prompt: str, max_tokens: int = 1800,) -> str:
    """
    Generate longer-form text (e.g., Substack article or blog post) using GPT.

    Args:
        prompt (str): User's input topic or query.
        max_tokens (int): Maximum tokens allowed in the GPT response (default: 1800).
        model (str): Model to use for generation (default: "gpt-4").

    Returns:
        str: Generated long-form text.
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": max_tokens,
    }

    try:
        response = make_gpt_request(payload, AZURE_DEPLOYMENT_ID)
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    except Exception as e:
        logging.error(f"Error generating GPT text: {e}")
        return ""