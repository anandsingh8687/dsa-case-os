# DSA Case OS - Quick Start Guide

## 🚀 Starting the System

### Option 1: Automated Startup (Recommended)
```bash
./START_SYSTEM.sh
```

This will:
- Start backend (API + Database)
- Wait for backend to be ready
- Start frontend
- Display access URLs

### Option 2: Manual Startup

**Backend:**
```bash
cd docker
docker-compose up -d
cd ..
```

**Frontend:**
```bash
cd frontend
npm install  # First time only
npm run dev
```

## 🔍 Check System Status

```bash
./CHECK_STATUS.sh
```

This shows:
- Docker container status
- Backend health
- Frontend status
- Database connectivity

## 🌐 Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **Frontend** | http://localhost:5173 | Main application UI |
| **Backend API** | http://localhost:8000 | REST API |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |

## 🔑 Testing Login Flow

### 1. **Visit Landing Page**
- Open: http://localhost:5173/
- Should see modern landing page with animations
- Click "Sign In" button

### 2. **Login**
- Use your registered credentials
- Or register a new account first

### 3. **After Login**
- Should redirect to: http://localhost:5173/dashboard
- Should see dashboard with stats, search, and cases

## 🐛 Troubleshooting

### Issue: "Dashboard not showing after login"

**Solution 1: Clear browser cache**
```bash
# Open browser DevTools (F12)
# Go to Application tab → Storage → Clear site data
# Or use incognito mode
```

**Solution 2: Check if backend is running**
```bash
./CHECK_STATUS.sh

# If backend not running:
cd docker
docker-compose up -d
```

**Solution 3: Check browser console for errors**
```bash
# Open DevTools (F12) → Console tab
# Look for red errors
# Common issues:
# - "Network Error" → Backend not running
# - "401 Unauthorized" → Token issue, try logging out and in again
# - "CORS Error" → Backend configuration issue
```

### Issue: "Port already in use"

**Frontend (5173):**
```bash
# Find process using port 5173
lsof -ti:5173

# Kill it
kill $(lsof -ti:5173)

# Restart frontend
cd frontend && npm run dev
```

**Backend (8000):**
```bash
# Stop and restart Docker containers
cd docker
docker-compose down
docker-compose up -d
```

### Issue: "Cannot connect to backend"

**Check backend logs:**
```bash
docker logs dsa_case_os_backend

# Check database logs:
docker logs dsa_case_os_db
```

**Restart backend:**
```bash
cd docker
docker-compose restart
```

### Issue: "Login works but dashboard is blank"

**Check browser console:**
1. Open DevTools (F12)
2. Go to Console tab
3. Look for API errors

**Verify token is saved:**
1. Open DevTools (F12)
2. Go to Application → Local Storage → http://localhost:5173
3. Should see `token` and `user` entries
4. If missing, login again

**Force reload:**
```bash
# In browser:
# Ctrl+Shift+R (Windows/Linux)
# Cmd+Shift+R (Mac)
```

## 📝 View Logs

**Frontend logs:**
```bash
tail -f frontend.log
```

**Backend logs:**
```bash
docker logs -f dsa_case_os_backend
```

**Database logs:**
```bash
docker logs -f dsa_case_os_db
```

## 🛑 Stopping the System

```bash
./STOP_SYSTEM.sh
```

Or manually:

**Stop frontend:**
```bash
kill $(cat frontend.pid)
# Or: kill $(lsof -ti:5173)
```

**Stop backend:**
```bash
cd docker
docker-compose down
```

## 🔄 Complete Reset

If nothing works, try a complete reset:

```bash
# 1. Stop everything
./STOP_SYSTEM.sh

# 2. Clean up
cd docker
docker-compose down -v  # Removes volumes too
cd ../frontend
rm -rf node_modules package-lock.json

# 3. Restart from scratch
cd ..
./START_SYSTEM.sh
```

## ✅ Verification Checklist

After starting the system, verify:

- [ ] Backend responds: `curl http://localhost:8000/api/v1/health`
- [ ] Frontend loads: Open http://localhost:5173
- [ ] Landing page displays correctly
- [ ] Can navigate to login page
- [ ] Can login successfully
- [ ] Dashboard appears after login
- [ ] Can create new case
- [ ] Can upload documents

## 📞 Common Commands

```bash
# Start system
./START_SYSTEM.sh

# Check status
./CHECK_STATUS.sh

# Stop system
./STOP_SYSTEM.sh

# View backend logs
docker logs -f dsa_case_os_backend

# View frontend logs
tail -f frontend.log

# Restart backend only
cd docker && docker-compose restart

# Restart frontend only
kill $(lsof -ti:5173) && cd frontend && npm run dev
```
