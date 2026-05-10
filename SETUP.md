# 🚀 5T Trading Bot - Auto Deployment Setup

## Only 3 Steps!

### Step 1: Create Droplet in DigitalOcean ⏱️ (2 min)

1. Go to https://cloud.digitalocean.com/
2. Click **Create** → **Droplets**
3. Select:
   - **Image:** Ubuntu 22.04 LTS
   - **Size:** $4-6/month (Basic)
   - **Region:** Nearest to you
   - **Auth:** Password (simpler) or SSH Key
4. Click **Create Droplet**
5. **Copy the IP address** when it's ready (e.g., `123.45.67.89`)

---

### Step 2: Add Droplet IP to GitHub Secrets ⏱️ (1 min)

1. Go to your GitHub repo: https://github.com/saurabh257257/5t
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Create secret:
   - **Name:** `DROPLET_IP`
   - **Value:** Paste your droplet IP (e.g., `123.45.67.89`)
5. Click **Add secret**

---

### Step 3: First Deployment ⏱️ (Auto, ~2 min)

Just push code to GitHub:

```bash
cd ~/Desktop/Claude/5t
git push origin main
```

**That's it!** GitHub Actions will:
- ✅ Connect to your droplet
- ✅ Clone the code
- ✅ Install Python & dependencies
- ✅ Start the bot
- ✅ Show dashboard URL

Check deployment progress:
1. Go to **Actions** tab on GitHub
2. Click the running workflow
3. Watch the logs

---

## 🌐 Access Your Bot

After deployment completes (2-3 min), open:

```
http://YOUR_DROPLET_IP:3000
```

You'll see your **holdings**, **P&L**, and **portfolio value**!

---

## Future Deployments

Every time you push to GitHub:

```bash
git add .
git commit -m "your message"
git push origin main
```

**Automatic deployment starts immediately!** ✨

---

## 🔧 Troubleshooting

### Deployment failed?
- Check GitHub Actions logs: **Actions** tab on GitHub
- Verify `DROPLET_IP` secret is correct
- Make sure droplet is running in DigitalOcean

### Can't access dashboard?
- Wait 2-3 minutes after deployment
- Check droplet is online in DigitalOcean
- Try: `http://YOUR_IP:3000` (not https)

### Need to check logs?
SSH into droplet:
```bash
ssh root@YOUR_DROPLET_IP
pm2 logs trading-bot
```

---

## 📝 Optional: SSH Key Auth (More Secure)

If using SSH key auth instead of password:

1. Generate SSH key on droplet:
```bash
ssh-keyscan -H YOUR_DROPLET_IP >> ~/.ssh/known_hosts
```

2. Get the private key and add to GitHub Secrets as `SSH_PRIVATE_KEY`

3. Update workflow to use it (already included!)

---

**You're all set!** 🎉

Just create droplet → add IP to secrets → push code → auto-deploy!
