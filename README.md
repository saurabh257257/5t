# 5T Trading Bot - Sensex Automation

Complete automated trading bot for Sensex with Android mobile app.

## Features

✅ **Real-time Sensex Monitoring** - Fetches price every 5 seconds
✅ **Support/Resistance Trading** - Automatic trade execution
✅ **Option Strike Selection** - 1000 points ITM in 100-point slots
✅ **Automated SL/TP** - 150 points SL, 450 points TP
✅ **Mobile App** - Android app for real-time monitoring
✅ **5Paisa Integration** - Direct API trade execution
✅ **GitHub Automation** - Auto-deploy on every push
✅ **24/7 Trading** - Runs on DigitalOcean Droplet

## Quick Start

### 1. Prerequisites
- DigitalOcean account
- GitHub account (saurabh257257)
- 5Paisa broker credentials

### 2. Deployment (Fully Automated!)

**Step 1: Add GitHub Secret**
```
Go to: https://github.com/saurabh257257/5t
Settings → Secrets and variables → Actions → New secret

Name: DIGITALOCEAN_TOKEN
Value: dop_v1_d5b93654e7f6521102de1178a1a8db7aeb51323dfbc6f0721f31b8e35bd766d1
```

**Step 2: Push Code**
```bash
cd 5t
git add .
git commit -m "Initial commit: 5T trading bot"
git push origin main
```

**Step 3: Watch It Deploy!**
- Go to Actions tab
- GitHub Actions will:
  - Create DigitalOcean Droplet
  - Install Node.js, npm, PM2
  - Clone code
  - Start trading bot
  - Droplet runs 24/7

## Project Structure

```
5t/
├── .github/
│   └── workflows/
│       └── deploy.yml           # GitHub Actions automation
├── terraform/
│   ├── main.tf                  # DigitalOcean Droplet config
│   └── init.sh                  # Server initialization script
├── server/
│   ├── app.js                   # Trading bot logic
│   └── package.json             # Node.js dependencies
├── android-app/                 # Kotlin Android app
├── .gitignore
└── README.md
```

## Trading Logic

### Support Level Detection
```
Price ≤ Support Level
↓
Stay at support for 5 minutes
↓
If bouncing UP → Buy CALL
If moving DOWN → Buy PUT
```

### Resistance Level Detection
```
Price ≥ Resistance Level
↓
Monitor direction
↓
If stays BELOW → Buy PUT (prepare to buy)
If bounces UP → Buy CALL
```

### Strike Price Calculation
```
Example: Sensex = 75,000
CALL Strike: 75,000 - 1,000 = 74,000 (rounded to 100-point slot)
PUT Strike: 75,000 + 1,000 = 76,000 (rounded to 100-point slot)
```

### Position Management
```
Entry Price: 75,500
↓
Stop Loss: Entry - 150 points = 75,350
↓
Take Profit: Entry + 450 points = 75,950
↓
Auto-close on either SL or TP hit
```

## Server API Endpoints

### Get Status
```bash
GET http://YOUR_DROPLET_IP:3000/api/status
```

Response:
```json
{
  "status": "running",
  "sensex": 75432.50,
  "support": 74500,
  "resistance": 76500,
  "lotSize": 1,
  "activeTrades": 2,
  "timestamp": "2024-05-10T10:30:00Z"
}
```

### Update Settings
```bash
POST http://YOUR_DROPLET_IP:3000/api/settings

{
  "support": 74500,
  "resistance": 76500,
  "lotSize": 1,
  "authKey": "your_daily_auth_key"
}
```

### Start Trading
```bash
POST http://YOUR_DROPLET_IP:3000/api/start
```

### Stop Trading
```bash
POST http://YOUR_DROPLET_IP:3000/api/stop
```

### Get Trade History
```bash
GET http://YOUR_DROPLET_IP:3000/api/trades
```

## Real-Time Updates

### WebSocket Connection
```javascript
const socket = io('http://YOUR_DROPLET_IP:3000');

socket.on('status', (data) => {
  console.log('Current Sensex:', data.sensex);
});

socket.on('trade', (data) => {
  console.log('Trade Executed:', data);
});

socket.on('trade_closed', (data) => {
  console.log('Trade Closed:', data);
});
```

## Monitoring

### Check Bot Logs
```bash
ssh root@YOUR_DROPLET_IP
pm2 logs trading-bot
```

### Bot Status
```bash
pm2 status
```

### Restart Bot
```bash
pm2 restart trading-bot
```

## Environment Variables

Create `.env` file in `server/` directory:

```
APP_NAME=5P58004979
APP_SOURCE=24930
USER_ID=47xt4VnND2x
PASSWORD=B356hBPBrAK
USER_KEY=PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp
ENCRYPTION_KEY=wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D
PORT=3000
```

## Troubleshooting

### Bot not starting?
```bash
ssh root@YOUR_DROPLET_IP
pm2 logs trading-bot
```

### Port 3000 blocked?
```bash
ufw allow 3000/tcp
```

### Check Droplet IP
```bash
In DigitalOcean Dashboard → Droplets → 5t-trading-bot → IP Address
```

### Redeploy
```bash
git push origin main
# GitHub Actions will automatically redeploy
```

## Security Notes

⚠️ **Keep your 5Paisa credentials safe!**
- Never commit .env file
- Use GitHub Secrets for sensitive data
- Use daily auth keys for mobile app access

## Support

For issues:
1. Check PM2 logs: `pm2 logs trading-bot`
2. Verify Sensex price API
3. Check DigitalOcean firewall settings
4. Review GitHub Actions workflow runs

## License

MIT

## Author

Saurabh Singh (@saurabh257257)

---

**Status:** ✅ Running 24/7 on DigitalOcean
**Last Updated:** 2026-05-10
