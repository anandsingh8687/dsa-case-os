# Urgent Fixes for credilo.in Deployment

## Problem 1: Frontend 502 Errors

Your frontend is showing 502 errors because Railway doesn't know how to serve the Vite app properly.

### Solution: Update These 3 Files

#### 1. Update `frontend/vite.config.js`
Replace the entire content with:
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
  },
})
```

#### 2. Update `frontend/package.json`
In the `"scripts"` section, add the `"start"` line:
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "start": "vite preview --host 0.0.0.0 --port 5173"
},
```

#### 3. Create `frontend/railway.json`
Create this new file:
```json
{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "npm install && npm run build"
  },
  "deploy": {
    "startCommand": "npm run start",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### After Making Changes:
```bash
git add frontend/
git commit -m "Fix frontend 502 errors - configure Vite for Railway"
git push
```

## Problem 2: DNS Configuration

### Current CNAME from Railway:
**`hwugy47y.up.railway.app`**

### Steps in GoDaddy:

1. **Login to GoDaddy** → Go to credilo.in domain

2. **Go to DNS Records** (NOT Domain Forwarding!)
   - Click: My Products → credilo.in → DNS → DNS Records

3. **Add/Edit CNAME for www:**
   - Type: `CNAME`
   - Name: `www`
   - Value: `hwugy47y.up.railway.app`
   - TTL: `600`

4. **Add CNAME for root domain:**
   - Type: `CNAME`
   - Name: `@`
   - Value: `hwugy47y.up.railway.app`
   - TTL: `600`

5. **Delete any conflicting records** - If you see existing www or @ records, delete them first

6. **Save and wait 5-30 minutes** for DNS to propagate

## What Happens After Both Fixes:

1. Push the code changes → Railway auto-deploys → Frontend 502 errors fixed
2. Add DNS records → Wait for propagation → credilo.in starts working
3. Both credilo.in and www.credilo.in will show your landing page!

## Quick Checklist:

- [ ] Update frontend/vite.config.js
- [ ] Update frontend/package.json (add start script)
- [ ] Create frontend/railway.json
- [ ] Commit and push to GitHub
- [ ] Wait 2-3 minutes for Railway to deploy
- [ ] Add CNAME records in GoDaddy DNS
- [ ] Wait 5-30 minutes for DNS propagation
- [ ] Test credilo.in and www.credilo.in

## GitHub Token Issue

Your GitHub token seems to be expired. If you can't push, you'll need to:
1. Go to GitHub.com → Settings → Developer settings → Personal access tokens
2. Generate new token (classic) with `repo` scope
3. Use it to push the changes

Or you can make these changes directly in Railway's GitHub UI or your local code editor.
