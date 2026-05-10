# 🚀 Deploy to DigitalOcean - Simple Steps

## Step 1: Create Droplet (Manual)

1. Go to https://cloud.digitalocean.com/
2. Click **Create** → **Droplets**
3. Select:
   - **Name:** `5t-holdings`
   - **Image:** Ubuntu 22.04 LTS
   - **Size:** $4-6/month
   - **Region:** Nearest to you
   - **Auth:** Password
4. Click **Create Droplet**
5. **Copy the IP address** when ready (e.g., `167.71.237.92`)
6. **Save the root password** from email

---

## Step 2: Add Droplet IP to GitHub

1. Go to: https://github.com/saurabh257257/5t/settings/secrets/actions
2. Click **New repository secret**
3. Create:
   - **Name:** `DROPLET_IP`
   - **Value:** Your droplet IP
4. Click **Add secret**

---

## Step 3: Add Droplet Password to GitHub

1. Same page as above
2. Click **New repository secret**
3. Create:
   - **Name:** `DROPLET_PASSWORD`
   - **Value:** Your root password from email
4. Click **Add secret**

---

## Step 4: Deploy

Just push code:

```bash
cd ~/Desktop/Claude/5t
git push origin main
```

**GitHub Actions will automatically:**
- ✅ Connect to droplet (using password)
- ✅ Clone code
- ✅ Install Python
- ✅ Start the server

---

## 🌐 Access Your App

After 2-3 minutes, open:

```
http://YOUR_DROPLET_IP:3000
```

You'll see your **holdings!** 📊

---

## 🔄 Future Updates

Every time you push:
```bash
git push origin main
```

**Auto-deploys in 2-3 minutes!**

---

## 📝 SSH Access (Optional)

To manually check the server:

```bash
ssh root@YOUR_DROPLET_IP
pm2 status
pm2 logs app
```
