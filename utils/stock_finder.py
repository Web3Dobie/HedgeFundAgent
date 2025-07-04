"""
Utility for finding relevant stock tickers based on keywords/themes using Azure OpenAI Service.
"""
import os
import logging
import re
import requests
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_RESOURCE_NAME = os.getenv("AZURE_RESOURCE_NAME")
AZURE_DEPLOYMENT_ID = os.getenv("AZURE_DEPLOYMENT_ID")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2025-03-01-preview")  # or your default

if not AZURE_RESOURCE_NAME or not AZURE_DEPLOYMENT_ID:
    logging.error("Azure config not loaded correctly in stock_finder! Check .env and load_dotenv.")
    raise ValueError("Azure config not loaded correctly!")

AZURE_ENDPOINT = f"https://{AZURE_RESOURCE_NAME}.openai.azure.com"

def validate_ticker(ticker: str) -> bool:
    """Validate ticker format ($SYMBOL with 1-5 alphanumeric chars after $)."""
    return bool(re.match(r"^\$[A-Z]{1,5}$", ticker))


def get_relevant_tickers(theme: str, max_tickers: int = 3) -> List[str]:
    """
    Use Azure GPT (via HTTP API) to identify relevant stock tickers for a given theme.
    Returns a list of cashtags (e.g., ['$XHB', '$LEN', '$DHI']).

    Args:
        theme (str): The keyword or theme to search for relevant tickers.
        max_tickers (int): Maximum number of tickers to return (default is 3).

    Returns:
        list[str]: List of validated stock tickers prefixed with "$".
    """
    try:
        # Construct the URL for the Azure OpenAI REST API endpoint
        url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_DEPLOYMENT_ID}/chat/completions?api-version={AZURE_API_VERSION}"


        # Define the system prompt and user's theme query
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a stock market expert. Given a theme, return ONLY the most relevant "
                        "US stock tickers. Always include 1 sector ETF first if available, then the top companies. "
                        "For example, for homebuilders return: $XHB $LEN $DHI\n"
                        "Return only tickers with $ prefix, separated by spaces. No explanation."
                    )
                },
                {
                    "role": "user",
                    "content": f"Return {max_tickers} most relevant tickers for: {theme}"
                }
            ],
            "max_tokens": 50,
            "temperature": 0.2  # Lower temperature for consistent results
        }

        # Include authorization and required headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AZURE_OPENAI_API_KEY}"
        }

        # Make the HTTP POST request
        response = requests.post(url, json=payload, headers=headers)

        # Check for HTTP errors
        response.raise_for_status()

        # Parse the response
        data = response.json()
        tickers = data["choices"][0]["message"]["content"].strip().split()

        # Validate tickers using the validation function
        valid_tickers = [t for t in tickers if validate_ticker(t)]

        # If no valid tickers are found, log a warning
        if not valid_tickers:
            logging.warning(f"No valid tickers found for theme: {theme}")
            return []

        # Return only up to `max_tickers` valid tickers
        return valid_tickers[:max_tickers]

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP Request failed: {e}")
        return []

    except Exception as e:
        logging.error(f"Error processing tickers: {e}")
        return []


# Example usage
if __name__ == "__main__":
    theme = "homebuilders"
    tickers = get_relevant_tickers(theme=theme)
    print("Relevant Tickers:", tickers)
