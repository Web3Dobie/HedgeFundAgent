# hedgefund_news_bridge.py - Add to HedgeFundAgent root directory
"""
This integrates with your existing HedgeFundAgent scheduler system
to create website-ready hedge fund news data for DutchBrat.com

Processes macro, equity, and political headlines from scored_headlines.csv
and creates a rotating feed for the website NewsCard component.
"""

import json
import os
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any
from urllib.parse import urlparse

# Import your existing HedgeFundAgent utilities
from utils.config import DATA_DIR
from utils.gpt import generate_gpt_text
from utils.logging_helper import get_module_logger

logger = get_module_logger(__name__)

class HedgeFundNewsProcessor:
    def __init__(self):
        self.headline_log = os.path.join(DATA_DIR, "scored_headlines.csv")
        self.output_file = os.path.join(DATA_DIR, "hedgefund_news_api.json")
    
    def extract_source_from_url(self, url: str) -> str:
        """Extract clean source name from URL"""
        try:
            domain = urlparse(url).netloc.lower()
            
            # Map domains to clean source names for hedge fund news sources
            source_map = {
                'reuters.com': 'reuters',
                'bloomberg.com': 'bloomberg',
                'wsj.com': 'wall_street_journal',
                'ft.com': 'financial_times',
                'cnbc.com': 'cnbc',
                'marketwatch.com': 'marketwatch',
                'yahoo.com': 'yahoo_finance',
                'finance.yahoo.com': 'yahoo_finance',
                'investing.com': 'investing',
                'seekingalpha.com': 'seeking_alpha',
                'barrons.com': 'barrons',
                'economist.com': 'economist',
                'zerohedge.com': 'zerohedge',
                'forexlive.com': 'forexlive',
                'federalreserve.gov': 'federal_reserve',
                'treasury.gov': 'us_treasury',
                'imf.org': 'imf',
                'worldbank.org': 'world_bank',
                'ecb.europa.eu': 'ecb',
                'boj.or.jp': 'bank_of_japan',
                'bankofengland.co.uk': 'bank_of_england',
                'politico.com': 'politico',
                'washingtonpost.com': 'washington_post',
                'nytimes.com': 'new_york_times',
                'foreign affairs.com': 'foreign_affairs'
            }
            
            # Remove www. prefix
            domain = domain.replace('www.', '')
            
            # Return mapped name or extract first part of domain
            return source_map.get(domain, domain.split('.')[0])
            
        except Exception as e:
            logger.warning(f"Error extracting source from URL {url}: {e}")
            return "unknown"
    
    def get_recent_headlines(self, hours: int = 2) -> List[Dict[str, Any]]:
        """
        Get recent headlines from the past N hours from scored_headlines.csv
        Filters for macro, equity, and political categories with scores >= 6
        """
        try:
            if not os.path.exists(self.headline_log):
                logger.warning(f"Headlines file not found: {self.headline_log}")
                return []
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_headlines = []
            
            with open(self.headline_log, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        # Parse timestamp
                        timestamp = datetime.fromisoformat(row.get('timestamp', ''))
                        
                        # Check if within time window
                        if timestamp < cutoff_time:
                            continue
                        
                        # Parse score
                        try:
                            score = float(row.get('score', 0))
                        except (ValueError, TypeError):
                            score = 0
                        
                        # Filter for relevant categories and minimum score
                        category = row.get('category', '').lower()
                        if category in ['macro', 'equity', 'political'] and score >= 6:
                            
                            # Extract source from URL
                            source = self.extract_source_from_url(row.get('url', ''))
                            
                            recent_headlines.append({
                                'headline': row.get('headline', ''),
                                'url': row.get('url', ''),
                                'score': score,
                                'timestamp': row.get('timestamp', ''),
                                'category': category,
                                'source': source
                            })
                            
                    except Exception as e:
                        logger.warning(f"Error processing row: {e}")
                        continue
            
            # Sort by score (highest first)
            recent_headlines.sort(key=lambda x: x['score'], reverse=True)
            
            logger.info(f"Found {len(recent_headlines)} recent hedge fund headlines")
            return recent_headlines
            
        except Exception as e:
            logger.error(f"Error reading headlines: {e}")
            return []
    
    def generate_dutchbrat_comment(self, headline: str, category: str) -> str:
        """
        Generate a witty, hedge fund-style comment from DutchBrat's perspective
        """
        prompt = f"""
        As DutchBrat, a hedge fund veteran with 30 years in TradFi, write a sharp, 
        insightful comment on this {category} headline. Keep it under 120 characters.
        Be clever, use market terminology, and show your experience. End with "— DutchBrat 🧠"
        
        Headline: {headline}
        Category: {category}
        
        Comment:
        """
        
        try:
            comment = generate_gpt_text(prompt, max_tokens=80)
            # Ensure it ends with DutchBrat's signature
            if "— DutchBrat 🧠" not in comment:
                comment += " — DutchBrat 🧠"
            return comment.strip()
        except Exception as e:
            logger.error(f"Error generating DutchBrat comment: {e}")
            # Fallback comments by category
            fallbacks = {
                'macro': "📊 This will move markets. Watch the vol spike. — DutchBrat 🧠",
                'equity': "💼 Classic sector rotation signal. Position accordingly. — DutchBrat 🧠", 
                'political': "🏛️ Policy implications are huge. Risk-off mode activated. — DutchBrat 🧠"
            }
            return fallbacks.get(category, "📈 Market moving news. Stay sharp. — DutchBrat 🧠")
    
    def process_and_export(self):
        """Process recent headlines and export for website API"""
        logger.info("🔄 Processing top 4 hedge fund headlines for DutchBrat rotation...")
        
        # Get recent headlines from past 2 hours
        headlines = self.get_recent_headlines(hours=2)
        
        if not headlines:
            logger.info("⚠️ No headlines found in past 2 hours, expanding to 6 hours...")
            # Fallback to last 6 hours if no recent headlines
            headlines = self.get_recent_headlines(hours=6)
        
        if not headlines:
            logger.warning("⚠️ No recent hedge fund headlines found")
            # Create empty structure
            output_data = {
                "success": True,
                "data": [],
                "lastUpdated": datetime.now().isoformat(),
                "message": "No recent hedge fund news available",
                "rotationSchedule": "20min intervals",
                "categories": ["macro", "equity", "political"]
            }
        else:
            # Generate DutchBrat comments for top 4 headlines
            processed_news = []
            for headline_data in headlines[:4]:  # Top 4 for 20-min rotation
                dutchbrat_comment = self.generate_dutchbrat_comment(
                    headline_data['headline'], 
                    headline_data['category']
                )
                
                processed_news.append({
                    "headline": headline_data['headline'],
                    "url": headline_data['url'],
                    "score": headline_data['score'],
                    "timestamp": headline_data['timestamp'],
                    "category": headline_data['category'],
                    "source": headline_data['source'],
                    "dutchbratComment": dutchbrat_comment
                })
            
            output_data = {
                "success": True,
                "data": processed_news,
                "lastUpdated": datetime.now().isoformat(),
                "totalHeadlines": len(headlines),
                "rotationSchedule": "20min intervals",
                "categories": list(set(h['category'] for h in headlines)),
                "message": f"Top {len(processed_news)} hedge fund headlines ready for rotation"
            }
        
        # Save to JSON file that the website API can read
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Hedge fund news rotation data exported to {self.output_file}")
            logger.info(f"📊 Headlines ready: {len(output_data.get('data', []))}")
            
            # Log categories and sources for debugging
            if output_data.get('data'):
                categories = [item['category'] for item in output_data['data']]
                sources = [item['source'] for item in output_data['data']]
                logger.info(f"🏷️ Categories: {list(set(categories))}")
                logger.info(f"🔍 Sources: {list(set(sources))}")
                
        except Exception as e:
            logger.error(f"❌ Error exporting hedge fund data: {e}")

# Create the processor instance
hedgefund_processor = HedgeFundNewsProcessor()

def generate_hedgefund_news_for_website():
    """
    Function to be called by the scheduler.
    Processes hedge fund headlines for DutchBrat website rotation.
    """
    try:
        hedgefund_processor.process_and_export()
    except Exception as e:
        logger.error(f"Error in hedge fund news processing: {e}")
        raise

# Additional function for manual testing
if __name__ == "__main__":
    print("🧠 Testing HedgeFund News Bridge...")
    generate_hedgefund_news_for_website()
    print("✅ Test completed!")