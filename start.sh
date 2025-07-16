#!/bin/bash
cd /home/azureuser/hedgefund

# Activate virtual environment
source venv/bin/activate

# Create necessary directories
mkdir -p data logs backup

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found! Please create it with your API keys."
    exit 1
fi

echo "✅ Environment ready"

# Start services via supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start all

# Start nginx
sudo systemctl restart nginx

echo "🚀 Hedge Fund Agent started!"
echo "📊 Health check: curl http://localhost:8080/health"
echo "📝 View logs: sudo supervisorctl tail -f hedgefund-scheduler"
