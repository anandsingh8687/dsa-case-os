# GoDaddy DNS Setup Guide for credilo.in

## Current Issue
The domain credilo.in shows "Application failed to respond" because DNS records are not configured yet.

## What Railway Gave You
- **CNAME Target:** `hwugy47y.up.railway.app`
- **Domains to configure:** credilo.in and www.credilo.in

## Step-by-Step Instructions

### Step 1: Navigate to DNS Records (NOT Domain Forwarding!)
1. Log into GoDaddy
2. Go to your domain credilo.in
3. Click on **DNS** tab
4. Click on **DNS Records** (NOT "Domain Forwarding")

### Step 2: Configure www.credilo.in
1. Look for existing CNAME record with name "www"
2. If it exists, click "Edit" or delete it
3. Add/Update CNAME record:
   - **Type:** CNAME
   - **Name:** www
   - **Value:** hwugy47y.up.railway.app
   - **TTL:** 600 (or default)
4. Save the record

### Step 3: Configure credilo.in (root domain)
For the root domain (@), you have two options:

**Option A: CNAME Flattening (if GoDaddy supports it)**
- **Type:** CNAME
- **Name:** @
- **Value:** nbw7yyme.up.railway.app
- **TTL:** 600

**Option B: A Record (if CNAME doesn't work for @)**
1. First, get Railway's IP address:
   - Go to Railway dashboard
   - Click on your frontend service
   - Settings → Networking → Check if there's an IP address
   - If not available, stick with Option A or contact Railway support

### Step 4: Wait for DNS Propagation
- Changes can take 5-30 minutes to propagate
- Sometimes up to 48 hours for full global propagation
- You can check status at: https://dnschecker.org

### Step 5: Verify
After DNS propagates, both should work:
- https://credilo.in
- https://www.credilo.in

Both should show your landing page without "Application failed to respond" error.

## Common Mistakes to Avoid
❌ Don't use "Domain Forwarding" - that redirects instead of pointing to Railway
❌ Don't add "https://" or "http://" in the CNAME value - just the hostname
❌ Make sure you're editing DNS Records, not other GoDaddy features

## Current Status
- ✅ Railway is configured and waiting for DNS
- ✅ Frontend is deployed and running
- ⏳ Waiting for you to add DNS records in GoDaddy
- ⏳ DNS propagation needed after records are added
