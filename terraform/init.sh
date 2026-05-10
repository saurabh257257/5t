#!/bin/bash
set -e

echo "🤖 Starting 5T Trading Bot Setup..."

# Update system
apt-get update
apt-get upgrade -y

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# Install Git
apt-get install -y git

# Install PM2 globally
npm install -g pm2

# Enable PM2 startup
pm2 startup -u root --hp /root
pm2 save

# Clone repository
cd /root
git clone ${github_repo} 5t || true
cd 5t/server

# Install dependencies
npm install

# Start the bot
pm2 start app.js --name "trading-bot"
pm2 save

# Configure firewall
ufw allow 3000/tcp || true
ufw enable -y || true

echo "✅ 5T Trading Bot is running!"
echo "Access at: http://$(hostname -I | awk '{print $1}'):3000"
