import os
import logging
from dotenv import load_dotenv
import tweepy

load_dotenv()
logging.basicConfig(level=logging.INFO)

client = tweepy.Client(
    consumer_key=os.getenv("X_API_KEY"),
    consumer_secret=os.getenv("X_API_SECRET"),
    access_token=os.getenv("X_ACCESS_TOKEN"),
    access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
)

resp = client.create_tweet(text="✅ Test tweet: permissions check")
logging.info(f"Response: {resp}")
