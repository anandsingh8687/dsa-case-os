# DSA Case OS — Deployment & Testing Guide

## Option 1: Local Testing (Fastest — 5 minutes)

### Prerequisites
- Docker Desktop installed ([download](https://www.docker.com/products/docker-desktop/))
- Git (optional)

### Steps

```bash
# 1. Navigate to the project
cd /path/to/dsa-case-os

# 2. Start everything with Docker Compose
cd docker
docker compose up -d --build

# 3. Wait for DB to initialize (30 seconds), then create tables
docker exec -i dsa_case_os_db psql -U postgres -d dsa_case_os < ../backend/app/db/schema.sql

# 4. Ingest lender data (run from backend container)
docker exec -it dsa_case_os_backend python -c "
import asyncio
from app.services.stages.stage3_ingestion import ingest_lender_policy_csv, ingest_pincode_csv

async def main():
    stats = await ingest_lender_policy_csv('/app/data/lender_policy.csv')
    print(f'Policy: {stats}')
    stats2 = await ingest_pincode_csv('/app/data/pincode_list.csv')
    print(f'Pincodes: {stats2}')

asyncio.run(main())
"
```

### What's running
| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8000 | FastAPI server |
| API Docs | http://localhost:8000/docs | Swagger UI (interactive) |
| Frontend | http://localhost:3000 | React app |
| PostgreSQL | localhost:5432 | Database |

### Quick Test (API Docs)
Open http://localhost:8000/docs in your browser.
This gives you an interactive Swagger UI to test every endpoint.

**Test flow:**
1. POST `/api/v1/auth/register` — create a user
2. POST `/api/v1/auth/login` — get JWT token
3. Click "Authorize" button, paste token
4. POST `/api/v1/cases/` — create a case
5. POST `/api/v1/cases/{case_id}/upload` — upload document PDFs
6. POST `/api/v1/extraction/case/{case_id}/extract` — run extraction
7. POST `/api/v1/eligibility/case/{case_id}/score` — run scoring
8. POST `/api/v1/reports/case/{case_id}/generate` — generate report
9. POST `/api/v1/copilot/query` — test the chatbot

---

## Option 2: Without Docker (Manual Setup)

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Tesseract OCR (`brew install tesseract` or `apt install tesseract-ocr`)

### Backend Setup

```bash
# 1. Create and activate virtualenv
cd backend
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create database
createdb dsa_case_os
psql -d dsa_case_os -f app/db/schema.sql

# 4. Configure environment
cp .env.example .env
# Edit .env — the Kimi API key is already set in .env

# 5. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## Option 3: Deploy to VPS for Team Testing (Shareable URL)

This gets you a URL like `https://caseos.yourdomain.in` that others can test.

### Recommended: DigitalOcean Droplet (₹3,000/month)

```bash
# 1. Create a droplet: Ubuntu 22.04, 4GB RAM, 2 vCPU

# 2. SSH into the server
ssh root@your-server-ip

# 3. Install Docker
curl -fsSL https://get.docker.com | sh

# 4. Clone or upload the project
# Option A: If on GitHub
git clone https://github.com/your-repo/dsa-case-os.git

# Option B: Upload with scp
scp -r ./dsa-case-os root@your-server-ip:/opt/dsa-case-os

# 5. Configure environment
cd /opt/dsa-case-os/backend
cp .env.example .env
nano .env
# Set your real values:
#   SECRET_KEY=generate-a-strong-random-key
#   LLM_API_KEY=sk-jOZ0CdgAROEkv0b5J1hd60mDQTTi44h00XHTsyJsPBEbVlU8
#   DEBUG=False

# 6. Start services
cd /opt/dsa-case-os/docker
docker compose up -d --build

# 7. Initialize database
docker exec -i dsa_case_os_db psql -U postgres -d dsa_case_os < ../backend/app/db/schema.sql

# 8. Set up Nginx reverse proxy + SSL
apt install nginx certbot python3-certbot-nginx -y

# Create Nginx config
cat > /etc/nginx/sites-available/caseos << 'NGINX'
server {
    server_name caseos.yourdomain.in;

    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
    }

    location / {
        proxy_pass http://localhost:3000/;
        proxy_set_header Host $host;
    }
}
NGINX

ln -s /etc/nginx/sites-available/caseos /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 9. Add SSL
certbot --nginx -d caseos.yourdomain.in
```

### Alternative: Railway.app (Easiest, Free Tier)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize project
cd dsa-case-os
railway init

# 4. Add PostgreSQL
railway add --plugin postgresql

# 5. Set environment variables
railway variables set LLM_API_KEY=sk-jOZ0CdgAROEkv0b5J1hd60mDQTTi44h00XHTsyJsPBEbVlU8
railway variables set LLM_BASE_URL=https://api.moonshot.cn/v1
railway variables set LLM_MODEL=kimi-latest
railway variables set SECRET_KEY=your-secret-key

# 6. Deploy
railway up

# Railway gives you a public URL like: dsa-case-os-production.up.railway.app
```

### Alternative: Render.com (Free Tier Available)

1. Push code to GitHub
2. Go to render.com → New Web Service
3. Connect your GitHub repo
4. Set build command: `pip install -r backend/requirements.txt`
5. Set start command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables (LLM_API_KEY, DATABASE_URL, SECRET_KEY)
7. Add PostgreSQL database from Render dashboard

---

## Ingesting Your Real Lender Data

After the server is running, load your lender policy and pincode data:

```bash
# Copy your CSV files to the server
scp "Lender policy/Lender Policy.xlsx - BL Lender Policy.csv" root@server:/opt/dsa-case-os/backend/data/lender_policy.csv
scp "Lender policy/Pincode list Lender Wise.csv" root@server:/opt/dsa-case-os/backend/data/pincode_list.csv

# Ingest via API (from your local machine)
curl -X POST http://your-server:8000/api/v1/lenders/ingest-policy \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@lender_policy.csv"

curl -X POST http://your-server:8000/api/v1/lenders/ingest-pincodes \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@pincode_list.csv"
```

---

## Sharing with Testers

Once deployed, share these with your 5 beta DSAs:

**What to share:**
1. URL: `https://caseos.yourdomain.in` (or Railway/Render URL)
2. Ask them to register with their email
3. Test flow: Upload real case documents → See checklist → Run scoring → Download report

**Feedback to collect:**
- Is classification accuracy good? (which docs got mis-classified)
- Are the right lenders showing up in eligibility?
- Is the report useful? What's missing?
- Copilot answers — relevant or not?

---

## Useful Commands

```bash
# View logs
docker compose logs -f backend

# Restart backend only
docker compose restart backend

# Check database
docker exec -it dsa_case_os_db psql -U postgres -d dsa_case_os
\dt              -- list tables
SELECT count(*) FROM lenders;
SELECT count(*) FROM lender_products;
SELECT count(*) FROM lender_pincodes;

# Run tests
docker exec -it dsa_case_os_backend pytest tests/ -v

# Check API health
curl http://localhost:8000/health
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DATABASE_URL | Yes | postgresql+asyncpg://... | PostgreSQL connection |
| SECRET_KEY | Yes | dev-secret... | JWT signing key |
| LLM_API_KEY | Yes | — | Kimi 2.5 API key (Moonshot AI) |
| LLM_BASE_URL | No | https://api.moonshot.cn/v1 | Kimi API endpoint |
| LLM_MODEL | No | kimi-latest | Kimi model name |
| STORAGE_BACKEND | No | local | "local" or "s3" |
| DEBUG | No | True | Debug mode |
