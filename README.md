# HedgeFundAgent

**HedgeFundAgent** is an automated agent for tweeting macro and equity opinions, running robust scheduled processes for ingesting news, generating posts, and maintaining logs.

## Project Structure and Module Overview

### Root

- **scheduler.py**  
  Orchestrates all scheduled tasks: news ingestion, commentary posting, deep dives, and log rotation.

### content/

- **hedgefund_commentary.py**  
  Posts regular hedge fund commentary to X/Twitter.
- **hedgefund_deep_dive.py**  
  Posts detailed, in-depth threads at scheduled times.

### utils/

- **\_\_init\_\_.py**  
  Marks the directory as a Python module.
- **config.py**  
  Loads and manages configuration and secrets.
- **gpt.py**  
  Integrates GPT/LLM for AI-generated content or summaries.
- **headline_pipeline.py**  
  Full pipeline for ingesting, processing, and ranking news headlines.
- **limit_guard.py**  
  Implements API rate limiting and usage safeguards.
- **logger.py**  
  Project-wide logging tools.
- **logging_helper.py**  
  Extra helpers for logging (formatters, handlers).
- **rotate_logs.py**  
  Rotates log files to manage disk usage.
- **rss_fetch.py**  
  Fetches and parses RSS news feeds.
- **scorer.py**  
  Scores headlines or content for relevance.
- **telegram_log_handler.py**  
  Sends logs or alerts to Telegram.
- **text_utils.py**  
  Miscellaneous text-processing utilities.
- **tg_notifier.py**  
  Sends messages or notifications to Telegram.
- **x_post.py**  
  Handles all posting to X/Twitter.

_This list may be incomplete. For the full, up-to-date file list, see the [utils directory on GitHub](https://github.com/Web3Dobie/HedgeFundAgent/tree/main/utils)._

## Installation

```sh
git clone https://github.com/Web3Dobie/HedgeFundAgent.git
cd HedgeFundAgent
pip install -r requirements.txt
```

## Configuration

1. Copy `.env.example` to `.env` and fill in the necessary API keys and secrets.
2. Edit `utils/config.py` as needed for advanced settings.

## Usage

To run the scheduler:
```sh
python scheduler.py
```
You can also run individual modules for testing.

## Contributing

Pull requests and issues are welcome! Please see the codebase for modular expansion points.

## License

MIT

---

*For more details on each module, please refer to the inline comments or docstrings within individual files.*