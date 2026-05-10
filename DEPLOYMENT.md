# Deployment Guide - 5T Trading Bot

## One-Click Deployment (Fully Automated)

### Prerequisites
✅ DigitalOcean account with API token
✅ GitHub account (saurabh257257)
✅ Repository: https://github.com/saurabh257257/5t

---

## Step 1: Add DigitalOcean Token to GitHub

1. Go to your GitHub repo: https://github.com/saurabh257257/5t
2. Click **Settings** tab
3. Left sidebar → **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. **Name:** `DIGITALOCEAN_TOKEN`
6. **Value:** Paste your token:
   ```
   dop_v1_d5b93654e7f6521102de1178a1a8db7aeb51323dfbc6f0721f31b8e35bd766d1
   ```
7. Click **Add secret**

---

## Step 2: Push Code to GitHub

```bash
# Navigate to your 5t directory
cd "C:/Users/Saurabh Singh/Desktop/Claude/5t"

# Initialize git (if not already done)
git init
git config user.email "saurabh257257@gmail.com"
git config user.name "Saurabh Singh"

# Add all files
git add .

# Commit
git commit -m "Initial commit: 5T Trading Bot with GitHub Actions automation"

# Add remote
git remote add origin https://github.com/saurabh257257/5t.git

# Push to GitHub
git push -u origin main
```

---

## Step 3: Watch GitHub Actions Deploy

1. Go to your repo: https://github.com/saurabh257257/5t
2. Click **Actions** tab
3. You'll see the workflow running
4. Wait ~5-10 minutes for:
   - ✅ Droplet created on DigitalOcean
   - ✅ Software installed (Node.js, Git, PM2)
   - ✅ Code cloned and deployed
   - ✅ Bot running 24/7

---

## Step 4: Get Your Droplet IP

### Option A: From DigitalOcean Dashboard
1. Go to https://cloud.digitalocean.com/droplets
2. Find "5t-trading-bot"
3. Copy the **IP Address**

### Option B: From GitHub Actions Output
1. Go to Actions tab
2. Click the latest successful run
3. Look for "Notify Deployment Success" step
4. IP address is in the output

---

## Step 5: Verify Bot is Running

```bash
# Test in your browser
http://YOUR_DROPLET_IP:3000
```

You should see:
```json
{
  "status": "running",
  "sensex": 75432.50,
  "support": 0,
  "resistance": 0,
  "activeTrades": 0,
  "timestamp": "2024-05-10T10:30:00Z"
}
```

---

## Step 6: Connect Your Android App

Update Android app with server URL:
```
http://YOUR_DROPLET_IP:3000
```

---

## Updating Code (Auto-Deploy)

Every time you make changes:

```bash
cd 5t

# Make changes to files...

# Commit and push
git add .
git commit -m "Description of changes"
git push origin main
```

**GitHub Actions will automatically:**
- ✅ Detect the push
- ✅ Update the Droplet code
- ✅ Restart the bot
- ✅ Done!

---

## Troubleshooting

### Workflow Failed?
1. Go to Actions tab
2. Click the failed run
3. Check the error logs
4. Fix the issue
5. Push again: `git push origin main`

### Droplet Not Created?
- Check GitHub Actions logs
- Verify DigitalOcean token is correct
- Check DigitalOcean account has payment method

### Can't Connect to Bot?
- Verify Droplet IP is correct
- Wait 2 minutes after creation
- Check firewall: `ufw allow 3000/tcp`
- SSH to server: `ssh root@YOUR_IP`
- Check logs: `pm2 logs trading-bot`

### SSH into Droplet (if needed)

```bash
ssh root@YOUR_DROPLET_IP
```

**View bot logs:**
```bash
pm2 logs trading-bot
```

**Restart bot:**
```bash
pm2 restart trading-bot
```

**Check status:**
```bash
pm2 status
```

---

## Cost Breakdown

| Item | Cost/Month |
|------|-----------|
| DigitalOcean Droplet | $4.00 |
| 5Paisa Broker | Free |
| GitHub Actions | Free |
| Total | $4.00 |

---

## Next Steps

1. ✅ Deploy (this guide)
2. Build Android app
3. Configure daily support/resistance
4. Start trading!

---

**Deployment Time:** 5-10 minutes ✅

---

For help:
- Check GitHub Actions logs
- SSH to server and check PM2 logs
- Review README.md
