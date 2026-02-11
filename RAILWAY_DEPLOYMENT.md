# 🚀 Railway Deployment Guide - DSA Case OS

## 📋 Prerequisites

1. ✅ GitHub account with repo: https://github.com/anandsingh8687/dsa-case-os
2. ✅ Railway account (sign up at https://railway.app)
3. ✅ Moonshot AI API key (for LLM features)

---

## 🎯 Architecture on Railway

```
┌─────────────────────────────────────────────┐
│         Railway Project                     │
│                                             │
│  ┌──────────────┐      ┌──────────────┐   │
│  │   Backend    │──────│  PostgreSQL  │   │
│  │   Service    │      │   Database   │   │
│  └──────┬───────┘      └──────────────┘   │
│         │                                   │
│  ┌──────▼───────┐                          │
│  │  WhatsApp    │                          │
│  │   Service    │                          │
│  └──────────────┘                          │
└─────────────────────────────────────────────┘
```

---

## 📝 Step-by-Step Deployment

### **Step 1: Sign Up for Railway**

1. Go to https://railway.app
2. Click **"Start a New Project"**
3. Sign in with GitHub
4. Authorize Railway to access your repositories

---

### **Step 2: Create New Project**

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose: `anandsingh8687/dsa-case-os`
4. Railway will detect the Dockerfile automatically

---

### **Step 3: Add PostgreSQL Database**

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway will automatically create database and set `DATABASE_URL`
4. **Note:** Railway auto-connects services - no manual config needed!

---

### **Step 4: Configure Backend Service**

1. Click on the **Backend service** (auto-created from Dockerfile)
2. Go to **"Variables"** tab
3. Add these environment variables:

```bash
# Required Variables
SECRET_KEY=<generate-with-openssl-rand-hex-32>
LLM_API_KEY=<your-moonshot-kimi-api-key>
LLM_MODEL=kimi-k2.5
LLM_BASE_URL=https://api.moonshot.cn/v1

# Optional but recommended
ENVIRONMENT=production
API_PREFIX=/api/v1
MAX_UPLOAD_SIZE_MB=50
```

4. **DATABASE_URL** is automatically set by Railway (check Variables tab)

---

### **Step 5: Deploy WhatsApp Service (Optional)**

**Note:** WhatsApp service requires persistent storage for sessions, which can be complex on Railway.

**Two Options:**

#### **Option A: Deploy Later (Recommended for initial testing)**
- Skip WhatsApp service for now
- Test core features first
- Add WhatsApp later when ready

#### **Option B: Deploy Now (Advanced)**
1. In Railway project, click **"+ New"**
2. Select **"GitHub Repo"** → Choose same repo
3. **Root Directory:** Set to `whatsapp-service`
4. **Dockerfile Path:** `whatsapp-service/Dockerfile`
5. Add environment variables:
```bash
PORT=3001
NODE_ENV=production
```

---

### **Step 6: Configure Domain (Optional)**

1. Click on Backend service
2. Go to **"Settings"** → **"Networking"**
3. Click **"Generate Domain"**
4. Railway will give you: `your-app-name.railway.app`
5. **Add to CORS:** Go back to Variables and add:
```bash
CORS_ORIGINS=["https://your-app-name.railway.app"]
```

---

### **Step 7: Deploy & Monitor**

1. Railway will automatically build and deploy
2. Check **"Deployments"** tab for progress
3. Check **"Logs"** tab for any errors
4. Wait for **"✓ Success"** status

---

## 🔍 Health Check

Once deployed, test these endpoints:

```bash
# Health check
https://your-app-name.railway.app/health

# API docs
https://your-app-name.railway.app/docs

# Frontend
https://your-app-name.railway.app/
```

---

## 💰 Cost Estimate

| Resource | Usage | Monthly Cost |
|----------|-------|--------------|
| **Hobby Plan** | Railway subscription | **$5** (includes $5 credit) |
| **Backend Service** | ~512MB RAM, minimal CPU | **~$5-10** |
| **PostgreSQL** | ~1GB storage | **~$5** |
| **WhatsApp Service** | ~512MB RAM | **~$5-10** (optional) |
| **Total (without WhatsApp)** | Backend + DB | **$10-15/month** |
| **Total (with WhatsApp)** | All services | **$15-25/month** |

**Free Credits:** $5/month free, so initial cost is ~$5-20/month

---

## 🔄 Auto-Deploy Setup

Railway automatically deploys when you push to `main` branch:

```bash
# Make changes locally
git add .
git commit -m "Update feature X"
git push origin main

# Railway automatically deploys! 🚀
```

---

## 🐛 Troubleshooting

### **Build Failed**
- Check **Logs** tab in Railway
- Verify Dockerfile is correct
- Check if all dependencies are in requirements.txt

### **Database Connection Error**
- Verify `DATABASE_URL` is set (should be automatic)
- Check PostgreSQL service is running
- Look for connection errors in logs

### **Application Crashes**
- Check **Logs** for Python errors
- Verify all environment variables are set
- Check if PORT variable is being used correctly

### **CORS Errors**
- Add your Railway domain to `CORS_ORIGINS`
- Format: `["https://your-app.railway.app"]`

---

## 🔐 Security Checklist

- ✅ Generate strong `SECRET_KEY` (use: `openssl rand -hex 32`)
- ✅ Keep `.env` files local (never commit)
- ✅ Use Railway's environment variables (encrypted)
- ✅ Set repository to **Private** on GitHub
- ✅ Enable Railway's automatic HTTPS
- ✅ Restrict CORS to your domain only

---

## 📊 Monitoring & Scaling

### **View Logs**
```
Railway Dashboard → Service → Logs tab
```

### **Monitor Resource Usage**
```
Railway Dashboard → Service → Metrics tab
```

### **Scale Up (if needed)**
```
Railway Dashboard → Service → Settings → Resources
- Increase RAM/CPU as needed
```

---

## 🆘 Support

- **Railway Docs:** https://docs.railway.app
- **Railway Discord:** https://discord.gg/railway
- **Moonshot AI Docs:** https://platform.moonshot.cn/docs

---

## 🎯 Next Steps After Deployment

1. ✅ Test all features on production URL
2. ✅ Set up error monitoring (Sentry - optional)
3. ✅ Configure custom domain (optional)
4. ✅ Set up backup strategy
5. ✅ Monitor costs and optimize

---

**Your Production URL will be:** `https://dsa-case-os-production.railway.app` (or similar)

**Deploy and test with real users! 🚀**
