# hedgefund_http_server.py - Add to HedgeFundAgent root directory
"""
HTTP server to serve hedge fund news data to the DutchBrat website
HedgeFundAgent runs on its own VM, separate from X-AI-Agent
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from utils.config import DATA_DIR
from utils.logging_helper import get_module_logger

logger = get_module_logger(__name__)

class HedgeFundNewsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/hedgefund-news-data':
            try:
                json_file = os.path.join(DATA_DIR, 'hedgefund_news_api.json')
                
                if os.path.exists(json_file):
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = f.read()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')  # Enable CORS
                    self.end_headers()
                    self.wfile.write(data.encode('utf-8'))
                    logger.info("✅ Served hedge fund news data via HTTP")
                else:
                    # Return empty but valid response
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    empty_response = {
                        "success": True,
                        "data": [],
                        "message": "No hedge fund news data available yet",
                        "categories": ["macro", "equity", "political"]
                    }
                    self.wfile.write(json.dumps(empty_response).encode('utf-8'))
                    logger.warning("⚠️ Hedge fund news data file not found, returned empty response")
                    
            except Exception as e:
                logger.error(f"❌ Error serving hedge fund news data: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                error_response = {
                    "success": False,
                    "error": "Internal server error"
                }
                self.wfile.write(json.dumps(error_response).encode('utf-8'))
                
        elif self.path == '/health':
            # Health check endpoint
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            health_response = {
                "status": "healthy",
                "service": "hedgefund-news",
                "timestamp": json.dumps({"$date": {"$numberLong": str(int(__import__('time').time() * 1000))}})
            }
            self.wfile.write(json.dumps(health_response).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            error_response = {
                "error": "Endpoint not found",
                "available_endpoints": ["/hedgefund-news-data", "/health"]
            }
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def log_message(self, format, *args):
        # Suppress default HTTP server logs (we use our own logger)
        pass

def start_hedgefund_news_server(port=3002):
    """Start the HTTP server for hedge fund news data only"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, HedgeFundNewsHandler)
    
    logger.info(f"🌐 Starting HedgeFund news HTTP server on port {port}")
    print(f"🌐 HedgeFund news server running on http://localhost:{port}")
    print(f"   🧠 HedgeFund news: http://localhost:{port}/hedgefund-news-data")
    print(f"   ❤️ Health check: http://localhost:{port}/health")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("🛑 HedgeFund news HTTP server stopped")
        httpd.shutdown()

if __name__ == "__main__":
    start_hedgefund_news_server()