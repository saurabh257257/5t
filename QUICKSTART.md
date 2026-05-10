# 🚀 Quick Start - 5T Trading Bot

Complete setup in 5 minutes!

---

## What You Need

✅ DigitalOcean account
✅ GitHub account (saurabh257257)
✅ This repo: https://github.com/saurabh257257/5t
✅ Your DigitalOcean API Token: `dop_v1_...`

---

## 5-Minute Setup

### Step 1: Add GitHub Secret (1 min)

1. Go to: https://github.com/saurabh257257/5t
2. Click **Settings**
3. **Secrets and variables** → **Actions**
4. **New repository secret**
   - Name: `DIGITALOCEAN_TOKEN`
   - Value: `dop_v1_d5b93654e7f6521102de1178a1a8db7aeb51323dfbc6f0721f31b8e35bd766d1`
5. **Add secret**

### Step 2: Initialize Local Repo (1 min)

```bash
cd "C:/Users/Saurabh Singh/Desktop/Claude/5t"
git init
git config user.email "saurabh257257@gmail.com"
git config user.name "Saurabh Singh"
git remote add origin https://github.com/saurabh257257/5t.git
```

### Step 3: Push Code (1 min)

```bash
git add .
git commit -m "Initial: 5T Trading Bot - Fully Automated"
git push -u origin main
```

### Step 4: Watch It Deploy (2 min)

1. Go to repo: https://github.com/saurabh257257/5t
2. Click **Actions** tab
3. Watch the workflow run
4. Wait for ✅ Success

---

## What Happens Automatically

✅ GitHub Actions detects your push
✅ Creates DigitalOcean Droplet ($4/month)
✅ Installs Node.js, PM2, Git
✅ Clones your code
✅ Starts trading bot
✅ Bot runs 24/7!

---

## Get Your Server URL

After deployment succeeds:

1. Go to: https://cloud.digitalocean.com/droplets
2. Find "5t-trading-bot"
3. Copy the **IP Address**
4. Your server: `http://YOUR_IP:3000`

---

## Test Your Bot

In browser:
```
http://YOUR_DROPLET_IP:3000
```

You should see:
```json
{
  "status": "running",
  "sensex": 75432.50
}
```

---

## Next: Build Android App

1. Download Android Studio: https://developer.android.com/studio
2. Open: `5t/android-app`
3. Update server URL in code
4. Run on your phone

---

## Update Bot Anytime

```bash
cd 5t

# Make changes...

git add .
git commit -m "Updated trading logic"
git push origin main

# GitHub Actions auto-deploys! ✅
```

---

## Check Bot Status

### View Logs
```bash
ssh root@YOUR_DROPLET_IP
pm2 logs trading-bot
```

### Restart Bot
```bash
pm2 restart trading-bot
```

### Check Droplet
```bash
pm2 status
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Actions failed | Check GitHub Actions logs |
| Can't reach bot | Wait 2 min, check firewall |
| Bot not trading | Check PM2 logs, verify settings |
| Need to redeploy | `git push origin main` |

---

## Cost

| Item | Cost |
|------|------|
| DigitalOcean Droplet | $4/month |
| Trading Bot | Free |
| **Total** | **$4/month** |

---

## Commands Cheat Sheet

```bash
# Deploy to GitHub (auto-deploys to Droplet)
git push origin main

# SSH into server
ssh root@YOUR_DROPLET_IP

# View bot logs
pm2 logs trading-bot

# Restart bot
pm2 restart trading-bot

# Stop bot
pm2 stop trading-bot

# Start bot
pm2 start trading-bot

# Check status
pm2 status
```

---

## API Endpoints

```bash
# Get status
curl http://YOUR_IP:3000/api/status

# Update settings
curl -X POST http://YOUR_IP:3000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "support": 74500,
    "resistance": 76500,
    "lotSize": 1,
    "authKey": "key"
  }'

# Start trading
curl -X POST http://YOUR_IP:3000/api/start

# Stop trading
curl -X POST http://YOUR_IP:3000/api/stop

# Get trades
curl http://YOUR_IP:3000/api/trades
```

---

## Directory Structure

```
5t/
├── .github/workflows/deploy.yml    # Auto-deploy on push
├── terraform/                       # Droplet config
├── server/                          # Node.js bot
├── android-app/                     # Mobile app
├── README.md                        # Full docs
├── DEPLOYMENT.md                    # Deploy guide
└── QUICKSTART.md                    # This file
```

---

## Done! 🎉

Your trading bot is now:
✅ Running on DigitalOcean 24/7
✅ Auto-deploying on GitHub push
✅ Ready for Android app
✅ Monitoring Sensex in real-time

**Next:** Build the Android app and start trading!

---

For detailed info:
- **Deployment:** See `DEPLOYMENT.md`
- **Architecture:** See `README.md`
- **Android App:** See `android-app/README.md`

---

**Questions?** Check GitHub Issues or SSH into server and review logs.

**Happy Trading! 🚀📈**
