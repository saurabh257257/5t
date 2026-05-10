#!/bin/bash

echo "🤖 Starting 5T Trading Bot Setup..."

# Update system
apt-get update -y
apt-get upgrade -y

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# Install Git
apt-get install -y git curl wget

# Install PM2 globally
npm install -g pm2 --silent

# Setup PM2 startup
pm2 startup -u root --hp /root > /dev/null 2>&1 || true
pm2 save

# Clone repository
cd /root
rm -rf 5t || true
git clone https://github.com/saurabh257257/5t.git 5t

# Navigate to server
cd /root/5t/server

# Create environment file
cat > .env << 'ENVEOF'
APP_NAME=5P58004979
APP_SOURCE=24930
USER_ID=47xt4VnND2x
PASSWORD=B356hBPBrAK
USER_KEY=PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp
ENCRYPTION_KEY=wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D
PORT=3000
NODE_ENV=production
ENVEOF

# Install dependencies
npm install --production

# Start the bot with PM2
pm2 delete trading-bot 2>/dev/null || true
pm2 start app.js --name "trading-bot" --instances 1 --exec-mode fork
pm2 save

# Configure firewall
ufw allow 3000/tcp 2>/dev/null || true
ufw enable -y 2>/dev/null || true

# Get IP address
IP_ADDR=$(hostname -I | awk '{print $1}')

echo "✅ 5T Trading Bot Setup Complete!"
echo "Access at: http://$IP_ADDR:3000"
echo "Status: $(pm2 status 2>/dev/null || echo 'PM2 running')"
