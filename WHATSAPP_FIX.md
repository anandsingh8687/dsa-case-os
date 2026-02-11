# 🔧 WhatsApp QR Generation Fix

## Problem
WhatsApp QR code generation failing with error: **"All connection attempts failed"**

## Root Cause
The `WHATSAPP_SERVICE_URL` environment variable was missing from:
1. `backend/app/core/config.py` - Settings class
2. `backend/.env` - Environment configuration

This caused the backend to try connecting to `http://localhost:3001` (default) instead of `http://whatsapp:3001` (Docker service name).

## Files Changed

### 1. `/backend/app/core/config.py`
Added WhatsApp service URL configuration:

```python
# WhatsApp Service
WHATSAPP_SERVICE_URL: str = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")
```

### 2. `/backend/.env`
Added environment variable:

```env
# WhatsApp Service (Node.js microservice)
WHATSAPP_SERVICE_URL=http://whatsapp:3001
```

## Deployment Steps

```bash
cd /Users/aparajitasharma/Downloads/dsa-case-os

# 1. Restart BOTH backend and WhatsApp services
docker compose -f docker/docker-compose.yml restart backend whatsapp

# 2. Check service health
docker compose -f docker/docker-compose.yml logs backend --tail 20
docker compose -f docker/docker-compose.yml logs whatsapp --tail 20

# 3. Verify WhatsApp service is reachable
docker compose -f docker/docker-compose.yml exec backend curl http://whatsapp:3001/health
```

Expected response from health check:
```json
{"status":"ok","service":"whatsapp","timestamp":"2026-02-11T..."}
```

## Testing Checklist

### ✅ Test 1: WhatsApp Service Health
1. Open browser to: http://localhost:8000
2. Open browser console (F12)
3. Run in console:
   ```javascript
   fetch('http://localhost:8000/api/v1/whatsapp/health')
     .then(r => r.json())
     .then(console.log)
   ```
4. **Expected**: `{status: "ok", whatsapp_service: "running"}`

### ✅ Test 2: QR Code Generation
1. Go to any case (VANASHREE ASSOCIATES or SHIVRAJ TRADERS)
2. Go to **Report** tab
3. Click **"Generate Report"** (if not already done)
4. Click **"📱 Send to Customer"** button
5. **Expected**:
   - QR code appears within 5-10 seconds
   - No errors in console
   - Status shows "Scan with WhatsApp"

### ✅ Test 3: QR Code Scanning
1. Open WhatsApp on your phone
2. Go to: Settings → Linked Devices → Link a Device
3. Scan the QR code shown in browser
4. **Expected**:
   - Modal shows "WhatsApp Linked Successfully!"
   - Phone number appears
   - "Send to Customer" button becomes active

### ✅ Test 4: Send Message
1. After linking WhatsApp (Test 3)
2. Click **"Send to Customer"** button
3. **Expected**:
   - Message sent successfully
   - Toast notification appears
   - Message appears on linked WhatsApp

## Architecture Overview

```
Frontend (Browser)
    ↓
Backend (FastAPI) :8000
    ↓ HTTP Request
    ↓ http://whatsapp:3001
    ↓
WhatsApp Service (Node.js + whatsapp-web.js) :3001
    ↓
WhatsApp Web Protocol
    ↓
WhatsApp Servers
```

## Common Issues & Solutions

### Issue 1: "Connection refused" or "Cannot connect"
**Cause**: WhatsApp service not running
**Solution**:
```bash
docker compose -f docker/docker-compose.yml ps whatsapp
docker compose -f docker/docker-compose.yml restart whatsapp
```

### Issue 2: "QR code expired"
**Cause**: QR code timeout after 60 seconds
**Solution**: Click "Generate QR Code" again to get a fresh code

### Issue 3: "Session not found"
**Cause**: WhatsApp service restarted, sessions lost
**Solution**:
- Sessions are stored in-memory
- Click "Generate QR Code" again
- Scan the new QR code

### Issue 4: Backend can't reach WhatsApp service
**Cause**: Wrong service URL or network issue
**Solution**:
```bash
# Check if backend can reach WhatsApp
docker compose -f docker/docker-compose.yml exec backend curl http://whatsapp:3001/health

# If it fails, check docker network
docker compose -f docker/docker-compose.yml ps
docker network ls
```

## Environment Variables Summary

| Variable | Value | Location |
|----------|-------|----------|
| `WHATSAPP_SERVICE_URL` | `http://whatsapp:3001` | backend/.env |
| `PORT` | `3001` | whatsapp-service/ (default) |

## Docker Compose Configuration

The services are connected via default Docker network:

```yaml
backend:
  depends_on:
    - whatsapp
  environment:
    - WHATSAPP_SERVICE_URL=http://whatsapp:3001

whatsapp:
  ports:
    - "3001:3001"
  volumes:
    - whatsapp_data:/app/.wwebjs_auth  # Persists WhatsApp sessions
```

## Logs to Check

### Backend Logs
```bash
docker compose -f docker/docker-compose.yml logs backend -f
```

Look for:
- `✅ "QR code generated for case CASE-..."`
- `❌ "WhatsApp service health check failed"`
- `❌ "Error generating QR code"`

### WhatsApp Service Logs
```bash
docker compose -f docker/docker-compose.yml logs whatsapp -f
```

Look for:
- `✅ "[CASE-...] QR code received"`
- `✅ "[CASE-...] WhatsApp client ready"`
- `❌ "Error initializing WhatsApp client"`

## Status: ✅ FIXED
- Configuration added
- Ready to test after backend restart

---

**Next Steps**:
1. Run deployment commands above
2. Test QR generation
3. Report results
