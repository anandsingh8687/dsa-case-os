# 🚀 QUICK START - Deploy to Railway in 15 Minutes

Follow these steps **exactly** to get your DSA Case OS live on the internet!

---

## ✅ STEP 1: Push Code to GitHub (You need to do this first!)

Run these commands **on your Mac terminal:**

```bash
# Navigate to project
cd /Users/aparajitasharma/Downloads/dsa-case-os

# Remove Git lock file (if needed)
rm -f .git/index.lock

# Stage all files
git add .

# Create commit
git commit -m "Initial commit: DSA Case OS complete system"

# Add GitHub remote
git remote add origin https://github.com/anandsingh8687/dsa-case-os.git

# Push to GitHub
git push -u origin main
```

**If GitHub asks for authentication:**
- Username: `anandsingh8687`
- Password: Use **Personal Access Token** (not your password!)
  - Get token from: https://github.com/settings/tokens
  - Click "Generate new token (classic)"
  - Select scope: `repo` (full control)
  - Copy the token and paste when asked for password

---

## ✅ STEP 2: Sign Up for Railway

1. Go to: **https://railway.app**
2. Click **"Login"**
3. Click **"Sign in with GitHub"**
4. Authorize Railway to access your GitHub repos

---

## ✅ STEP 3: Create New Project on Railway

1. Click **"New Project"**
2. Click **"Deploy from GitHub repo"**
3. Search and select: **`dsa-case-os`**
4. Railway will start building automatically! ⏳

**Wait ~5 minutes for build to complete**

---

## ✅ STEP 4: Add PostgreSQL Database

1. In your Railway project dashboard, click **"+ New"**
2. Select **"Database"**
3. Click **"Add PostgreSQL"**
4. Done! Railway automatically connects it to your backend 🎉

---

## ✅ STEP 5: Get Your Moonshot AI API Key

1. Go to: **https://platform.moonshot.cn/**
2. Sign up / Log in
3. Go to **API Keys** section
4. Create new API key
5. **Copy the key** (you'll need it in next step)

---

## ✅ STEP 6: Add Environment Variables

1. Click on your **Backend service** in Railway
2. Click **"Variables"** tab
3. Click **"+ New Variable"**
4. Add these one by one:

```
Variable Name: SECRET_KEY
Value: <run this command on Mac: openssl rand -hex 32>

Variable Name: LLM_API_KEY
Value: <paste your Moonshot API key from Step 5>

Variable Name: LLM_MODEL
Value: kimi-k2.5

Variable Name: LLM_BASE_URL
Value: https://api.moonshot.cn/v1

Variable Name: ENVIRONMENT
Value: production

Variable Name: API_PREFIX
Value: /api/v1
```

5. Click **"Deploy"** to restart with new variables

---

## ✅ STEP 7: Get Your Public URL

1. Click on your **Backend service**
2. Go to **"Settings"** tab
3. Scroll to **"Networking"**
4. Click **"Generate Domain"**
5. Railway will give you a URL like: `https://dsa-case-os-production.up.railway.app`

**Copy this URL!** This is your production URL 🎉

---

## ✅ STEP 8: Update CORS Settings

1. Go back to **"Variables"** tab
2. Add one more variable:

```
Variable Name: CORS_ORIGINS
Value: ["https://your-generated-domain.railway.app"]
```

Replace `your-generated-domain` with the actual URL from Step 7

3. Click **"Deploy"** again

---

## ✅ STEP 9: Test Your Application! 🎉

Open your Railway URL in a browser:

```
https://your-app-name.railway.app
```

**Test these:**
1. ✅ Home page loads
2. ✅ Register new account
3. ✅ Login with credentials
4. ✅ Create new case
5. ✅ Upload documents
6. ✅ Check API docs: `https://your-url.railway.app/docs`

---

## 🎯 Your App is Now LIVE!

Share this URL with your users:
```
https://your-app-name.railway.app
```

---

## 💰 What You're Paying

- **Railway Hobby Plan:** $5/month (includes $5 free credit)
- **Backend Service:** ~$5-10/month
- **PostgreSQL Database:** ~$5/month
- **Total:** ~$10-15/month for unlimited users! 🎉

---

## 🔄 How to Make Changes Later

When you want to add features or fix bugs:

```bash
# On your Mac terminal
cd /Users/aparajitasharma/Downloads/dsa-case-os

# Make changes (or let Claude make changes via Cowork)

# Commit and push
git add .
git commit -m "Your change description"
git push origin main

# Railway automatically deploys! 🚀
# Wait 3-5 minutes for deployment
```

---

## 🐛 Troubleshooting

### **"Build Failed"**
- Check **Deployments** tab → **View Logs**
- Look for error messages
- Most common: Missing environment variables

### **"Cannot connect to database"**
- Make sure PostgreSQL service is running (should show green checkmark)
- Check that `DATABASE_URL` is in Variables (Railway sets this automatically)

### **"CORS Error"**
- Make sure you added `CORS_ORIGINS` variable
- Format must be: `["https://your-domain.railway.app"]` (with quotes and brackets!)

### **"LLM API Error"**
- Check your Moonshot AI API key is valid
- Make sure you have credits in your Moonshot account
- Verify `LLM_API_KEY` is set correctly in Variables

---

## 📞 Need Help?

- **Railway Discord:** https://discord.gg/railway
- **Railway Docs:** https://docs.railway.app
- **Email Anand:** anandsingh8687@gmail.com

---

## 🎉 CONGRATULATIONS!

You've successfully deployed a production-ready AI loan processing system!

**What you can do now:**
- ✅ Share URL with DSA agents
- ✅ Process real loan applications
- ✅ Get feedback from users
- ✅ Iterate and improve with Claude's help

---

**Your journey from local to production: COMPLETE! 🚀**
