#!/bin/bash

# Manual deployment script for 5T Trading Bot
# Run this on your local machine to deploy to the droplet

DROPLET_IP="143.244.140.57"
SSH_USER="root"
SSH_KEY="$HOME/.ssh/id_ed25519"

echo "🚀 5T Trading Bot - Manual Deployment"
echo "======================================"
echo ""

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found at: $SSH_KEY"
    echo "Please add your SSH key first"
    exit 1
fi

echo "✅ SSH key found"
echo "📍 Deploying to: $DROPLET_IP"
echo ""

# Deploy script
DEPLOY_SCRIPT='
set -e

echo "🤖 Deploying 5T Trading Bot..."

# Check network
echo "Checking network..."
for i in {1..10}; do
    if ping -c 1 8.8.8.8 &> /dev/null; then
        echo "✅ Network ready"
        break
    fi
    sleep 2
done

# Clone/update repo
if [ ! -d "/root/5t" ]; then
    echo "Cloning repository..."
    cd /root
    git clone https://github.com/saurabh257257/5t.git 5t
else
    echo "Updating repository..."
    cd /root/5t
    git pull origin main
fi

cd /root/5t/server

# Install Python if needed
if ! command -v python3 &> /dev/null; then
    echo "Installing Python3..."
    apt-get update
    apt-get install -y python3 python3-pip python3-venv
fi

# Create virtual environment
echo "Setting up Python environment..."
python3 -m venv venv || true
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install PM2 for Node
if ! command -v pm2 &> /dev/null; then
    echo "Installing PM2..."
    npm install -g pm2 2>/dev/null || (apt-get install -y npm && npm install -g pm2)
fi

# Start bot
echo "Starting bot..."
pm2 delete trading-bot 2>/dev/null || true
pm2 start "python3 app.py" --name trading-bot --interpreter none
pm2 save

echo "✅ Bot deployed successfully!"
echo ""
echo "Check status:"
echo "  pm2 status"
echo ""
echo "View logs:"
echo "  pm2 logs trading-bot"
echo ""
echo "Dashboard: http://143.244.140.57:3000"
'

# Execute deployment
echo "🔑 Connecting via SSH..."
ssh -i "$SSH_KEY" "$SSH_USER@$DROPLET_IP" "$DEPLOY_SCRIPT"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "Your dashboard is live at:"
    echo "  🌐 http://143.244.140.57:3000"
    echo ""
    echo "Holdings page:"
    echo "  📊 http://143.244.140.57:3000/holdings.html"
else
    echo ""
    echo "❌ Deployment failed!"
    echo "Check your droplet is running and SSH key is correct"
fi
