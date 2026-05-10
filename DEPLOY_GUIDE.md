# 🚀 5T Trading Bot - Step-by-Step Deployment Guide

## Step 1: Create New DigitalOcean Droplet

### 1.1 Create Droplet
1. Go to https://cloud.digitalocean.com/
2. Click **Create** → **Droplets**
3. Choose:
   - **Image:** Ubuntu 22.04 LTS
   - **Size:** Basic ($4-6/month minimum)
   - **Region:** Choose closest to you (e.g., Singapore, India)
   - **Authentication:** SSH Key (recommended) OR Password
   - **Hostname:** `5t-trading-bot`

4. Click **Create Droplet**
5. **Wait 1-2 minutes** for droplet to start
6. **Copy the IP address** (e.g., `123.45.67.89`)

### 1.2 Connect to Droplet

**Option A: SSH Key (Recommended)**
```bash
ssh root@YOUR_DROPLET_IP
```

**Option B: Password**
```bash
ssh root@YOUR_DROPLET_IP
# Enter password when prompted
```

---

## Step 2: Setup Server on Droplet

Once connected via SSH, run these commands:

### 2.1 Update System
```bash
apt-get update
apt-get upgrade -y
```

### 2.2 Install Python & Dependencies
```bash
apt-get install -y python3 python3-pip python3-venv git
```

### 2.3 Clone Repository
```bash
cd /root
git clone https://github.com/saurabh257257/5t.git
cd 5t/server
```

### 2.4 Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2.5 Install Python Requirements
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.6 Setup Environment Variables
```bash
cp .env.example .env
nano .env
```

**Important:** Make sure all credentials are correct:
- APP_NAME
- APP_SOURCE
- USER_ID
- PASSWORD
- USER_KEY
- ENCRYPTION_KEY

Save with: `Ctrl + X`, then `Y`, then `Enter`

### 2.7 Install PM2 (Process Manager)
```bash
apt-get install -y npm
npm install -g pm2
```

### 2.8 Start the Bot
```bash
pm2 start "python3 app.py" --name trading-bot
pm2 startup
pm2 save
```

### 2.9 Check Status
```bash
pm2 status
pm2 logs trading-bot
```

You should see: `✅ 5Paisa client connected`

---

## Step 3: Access Your Dashboard

Open browser and go to:
```
http://YOUR_DROPLET_IP:3000
```

You should see your holdings displayed!

---

## Step 4: Setup Auto-Deployment (Optional)

To auto-deploy when you push to GitHub:

### 4.1 Add SSH Key to GitHub
```bash
# On your droplet, generate SSH key for GitHub
ssh-keygen -t ed25519 -f /root/.ssh/github_key -N ""

# Print the key
cat /root/.ssh/github_key.pub
```

Copy the output and add to GitHub:
1. Go to https://github.com/settings/keys
2. Click **New SSH Key**
3. Paste the key
4. Save

### 4.2 Create GitHub Actions Workflow

On your local machine, create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Droplet

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy via SSH
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          DROPLET_IP: ${{ secrets.DROPLET_IP }}
        run: |
          mkdir -p ~/.ssh
          echo "$SSH_PRIVATE_KEY" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H $DROPLET_IP >> ~/.ssh/known_hosts
          
          ssh -i ~/.ssh/id_ed25519 root@$DROPLET_IP << 'EOF'
          cd /root/5t
          git pull origin main
          cd server
          source venv/bin/activate
          pip install -r requirements.txt
          pm2 restart trading-bot
          EOF
```

Then add GitHub Secrets:
1. Go to repo → Settings → Secrets
2. Add `DROPLET_IP` = your droplet IP
3. Add `SSH_PRIVATE_KEY` = content of `/root/.ssh/github_key`

---

## Useful Commands

### View Logs
```bash
pm2 logs trading-bot
```

### Restart Bot
```bash
pm2 restart trading-bot
```

### Stop Bot
```bash
pm2 stop trading-bot
```

### Update Code
```bash
cd /root/5t
git pull origin main
cd server
source venv/bin/activate
pip install -r requirements.txt
pm2 restart trading-bot
```

### Check Port 3000
```bash
netstat -tlnp | grep 3000
```

---

## Troubleshooting

### "5Paisa client not connected"
- Check `.env` file has correct credentials
- Verify `app.py` has no errors: `python3 app.py`

### "Port 3000 already in use"
```bash
lsof -i :3000
kill -9 <PID>
```

### "Module not found" errors
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "Permission denied" on SSH
- Check SSH key has correct permissions: `chmod 600 ~/.ssh/id_ed25519`
- Verify droplet allows SSH (check firewall)

---

## Dashboard Features

✅ **Real-time Holdings** - See all your positions
✅ **P&L Calculation** - Profit/Loss for each holding
✅ **Portfolio Value** - Total holdings value
✅ **Auto-Refresh** - Updates every 30 seconds
✅ **Beautiful UI** - Works on desktop, tablet, phone

---

## Next Steps

1. ✅ Create droplet
2. ✅ Deploy server
3. ✅ Access dashboard at `http://YOUR_IP:3000`
4. ✅ (Optional) Setup auto-deployment

---

**Your dashboard is now live!** 🎉

For support or issues, check the logs with: `pm2 logs trading-bot`
