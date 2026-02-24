# 🏦 DSA Case OS - Digital Credit Intelligence Platform

> **AI-powered loan processing system for Direct Selling Agents (DSAs)**
> Built with FastAPI, PostgreSQL, WhatsApp Integration, and LLM-powered insights

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)

---

## 🚀 Features

## ✅ 2026 Platform Update (Current)

- Multi-tenant organizations with role-based access:
  - `super_admin`, `dsa_owner`, `agent`
- Organization management APIs:
  - `POST /api/v1/organizations`
  - `POST /api/v1/organizations/{organization_id}/owners`
  - `POST /api/v1/organizations/{organization_id}/agents`
- RAG policy intelligence with pgvector:
  - `POST /api/v1/rag/ingest`
  - `POST /api/v1/rag/search`
  - CLI script: `backend/scripts/ingest_lender_docs.py`
- Redis + RQ background processing path:
  - Worker entry: `backend/worker.py`
  - Admin queue snapshot: `GET /api/v1/admin/rq`
- WhatsApp Cloud API support (primary number: `8130781881`)
  - Webhook verify: `GET /api/v1/whatsapp/webhook`
  - Webhook events: `POST /api/v1/whatsapp/webhook`
  - Cloud send: `POST /api/v1/whatsapp/cloud/send-message`
- Quick Forward Help page in frontend:
  - Route: `/quick-forward-help`

### 🎯 **Core Capabilities**
- ✅ **Automated Document Processing** - OCR extraction from PDFs, images, bank statements
- ✅ **Intelligent Classification** - AI-powered document type detection
- ✅ **30+ Lender Integration** - Eligibility matching across multiple lenders
- ✅ **Smart Recommendations** - LLM-generated submission strategies
- ✅ **WhatsApp Integration** - Send reports and communicate with customers
- ✅ **Bank Statement Analyzer** - External API integration for financial analysis
- ✅ **Copilot Chatbot** - Query lender policies, CIBIL requirements, pincodes
- ✅ **Real-time Pipeline** - Multi-stage async processing with live updates

### 📊 **Business Features**
- Multi-user DSA workspace
- Case management dashboard
- Document checklist automation
- Lender match scoring (probability + ticket size)
- Missing document detection
- GST-based turnover extraction
- CIBIL score analysis
- Comprehensive PDF reports

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)             │
│              Single-page application with               │
│         Dashboard, Case Management, Reports             │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │   FastAPI Backend     │
         │   ┌───────────────┐  │
         │   │  Stage 1: OCR │  │
         │   ├───────────────┤  │
         │   │  Stage 2: Doc │  │
         │   │  Classifier   │  │
         │   ├───────────────┤  │
         │   │  Stage 3: Data│  │
         │   │  Extraction   │  │
         │   ├───────────────┤  │
         │   │  Stage 4: GST │  │
         │   │  Processing   │  │
         │   ├───────────────┤  │
         │   │  Stage 5:     │  │
         │   │  Eligibility  │  │
         │   ├───────────────┤  │
         │   │  Stage 6: LLM │  │
         │   │  Report Gen   │  │
         │   ├───────────────┤  │
         │   │  Stage 7:     │  │
         │   │  Copilot      │  │
         │   └───────────────┘  │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  PostgreSQL Database  │
         │  - Users, Cases       │
         │  - Documents          │
         │  - Lenders, Policies  │
         │  - Eligibility Data   │
         └───────────────────────┘

         ┌───────────────────────┐
         │  WhatsApp Service     │
         │  (Node.js + Puppeteer)│
         │  - QR Code Auth       │
         │  - Message Sending    │
         └───────────────────────┘
```

---

## 🛠️ Tech Stack

### **Backend**
- **Framework:** FastAPI (async Python)
- **Database:** PostgreSQL with asyncpg
- **OCR:** Tesseract
- **LLM:** Moonshot AI (Kimi K2.5)
- **Document Processing:** PyMuPDF, Pillow
- **Authentication:** JWT tokens

### **Frontend**
- **Framework:** React + Vite
- **UI:** TailwindCSS
- **Icons:** Lucide

### **Services**
- **WhatsApp:** Node.js + whatsapp-web.js + Puppeteer
- **Bank Analyzer:** External API integration

---

## 📦 Quick Start

### **Option 1: Deploy to Railway (Production)**

See [RAILWAY_DEPLOYMENT.md](./RAILWAY_DEPLOYMENT.md) for complete guide.

**Quick Deploy:**
1. Sign up at https://railway.app
2. Connect GitHub repo
3. Add PostgreSQL database
4. Set environment variables
5. Deploy! 🚀

**Cost:** ~$10-15/month

---

### **Option 2: Local Development (Docker)**

```bash
# Clone repository
git clone https://github.com/anandsingh8687/dsa-case-os.git
cd dsa-case-os

# Copy environment variables
cp backend/.env.example backend/.env
cp docker/.env.example docker/.env

# Edit .env files with your API keys

# Start services
cd docker
docker compose up -d

# Access application
open http://localhost:8000
```

### Background Worker (Required For Queue Mode)

`docker-compose` now includes:
- `db` (pgvector-enabled Postgres)
- `redis`
- `backend`
- `worker`

Set these env values for queue mode:

```bash
RQ_ASYNC_ENABLED=true
REDIS_URL=redis://redis:6379/0
DOC_QUEUE_ENABLED=false
```

If `RQ_ASYNC_ENABLED=false`, the legacy in-process DB queue worker is used.

---

## 🔧 Configuration

### **Required Environment Variables**

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/dsa_case_os

# JWT Secret (generate with: openssl rand -hex 32)
SECRET_KEY=your-secret-key-here

# LLM API (Moonshot AI - Kimi)
LLM_API_KEY=your-kimi-api-key
LLM_MODEL=kimi-k2.5
LLM_BASE_URL=https://api.moonshot.cn/v1

# WhatsApp Cloud API (Meta)
WHATSAPP_CLOUD_ACCESS_TOKEN=...
WHATSAPP_CLOUD_PHONE_NUMBER_ID=...
WHATSAPP_CLOUD_VERIFY_TOKEN=credilo-whatsapp-verify
WHATSAPP_CLOUD_BUSINESS_NUMBER=8130781881

# Queue
REDIS_URL=redis://localhost:6379/0
RQ_ASYNC_ENABLED=true
```

See `.env.example` for complete list.

---

## 📚 API Documentation

Once deployed, access interactive API docs:

- **Swagger UI:** `https://your-domain.com/docs`
- **ReDoc:** `https://your-domain.com/redoc`

### **Key Endpoints**

```
POST   /api/v1/auth/register          - Create new user account
POST   /api/v1/auth/login             - Login and get JWT token
GET    /api/v1/cases                  - List all cases
POST   /api/v1/cases                  - Create new case
POST   /api/v1/cases/{id}/upload      - Upload documents
POST   /api/v1/cases/{id}/pipeline/trigger - Trigger async full pipeline
GET    /api/v1/cases/{id}/report      - Get AI-generated report
POST   /api/v1/copilot/chat           - Chat with lender copilot
POST   /api/v1/whatsapp/generate-qr   - Generate WhatsApp QR code
POST   /api/v1/whatsapp/send-message  - Send WhatsApp message
POST   /api/v1/whatsapp/cloud/send-message - Send via Meta Cloud API
GET    /api/v1/whatsapp/webhook       - Meta webhook verify
POST   /api/v1/whatsapp/webhook       - Meta webhook receiver
POST   /api/v1/bank-statement/process - Process bank statements
POST   /api/v1/verify/rag             - Validate RAG retrieval quality
POST   /api/v1/verify/auto            - Validate prefill + async pipeline
```

---

## 🚆 Railway Deployment (Updated)

1. Backend service:
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Worker service (same repo, same env):
   - Start command: `python worker.py`
3. Add Railway Postgres and Redis services.
4. Set env vars on backend + worker:
   - `DATABASE_URL`, `DATABASE_URL_SYNC`, `SECRET_KEY`
   - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
   - `REDIS_URL`, `RQ_ASYNC_ENABLED=true`, `DOC_QUEUE_ENABLED=false`
   - `WHATSAPP_CLOUD_ACCESS_TOKEN`, `WHATSAPP_CLOUD_PHONE_NUMBER_ID`, `WHATSAPP_CLOUD_VERIFY_TOKEN`, `WHATSAPP_CLOUD_BUSINESS_NUMBER=8130781881`
5. Meta webhook setup:
   - Webhook URL: `https://<backend-domain>/api/v1/whatsapp/webhook`
   - Verify token: same as `WHATSAPP_CLOUD_VERIFY_TOKEN`
   - Subscribe message events for the configured phone number ID.
6. Ingest lender policy docs:
   - API: `POST /api/v1/rag/ingest`
   - or script: `python backend/scripts/ingest_lender_docs.py --organization-id <uuid>`

---

## 🎯 Usage Flow

### **For DSA Agents:**

1. **Register/Login** → Create account
2. **New Case** → Enter borrower details
3. **Upload Docs** → Upload bank statements, ITR, GST, etc.
4. **Auto-Process** → System extracts data and classifies documents
5. **Review Results** → Check eligibility across 30+ lenders
6. **Get Report** → AI-generated submission strategy
7. **Send to Customer** → WhatsApp integration for easy sharing

### **Current Fast Case Flow (GST-first + Async)**

1. `New Case` → choose either:
   - `Run Quick Scan` (no docs)
   - `Upload Documents` (GST-first prefill)
2. On document upload:
   - GST candidate docs are scanned first
   - GSTIN is extracted quickly
   - GST API pre-fills Company Name / Entity / Pincode / Address
3. Heavy steps (OCR/classification/extraction/scoring/report) run in RQ background queue.
4. Case detail page shows queue progress and keeps summary/report auto-refreshing.
5. Email collaboration uses secure temporary share links instead of large attachments.

### **Copilot Queries:**

- "Which lenders fund below 650 CIBIL?"
- "Show me lenders in pincode 400001"
- "Compare Bajaj vs IIFL for business loans"
- "Which lenders have minimum 1 year vintage?"

---

## 🔐 Security

- ✅ JWT-based authentication
- ✅ Password hashing with bcrypt
- ✅ Environment variable protection
- ✅ SQL injection prevention (parameterized queries)
- ✅ CORS configuration
- ✅ Input validation with Pydantic
- ✅ Secrets excluded from Git (see .gitignore)

---

## 📈 Scaling

### **Railway (Recommended for start)**
- Start: $10-15/month (100-500 users)
- Scale: $50-100/month (1000-5000 users)
- Easy vertical scaling (more RAM/CPU)

### **Future Optimization**
- Redis caching for lender policies
- CDN for static files (Cloudflare)
- Database read replicas
- Background job queues (Celery)
- Kubernetes for high scale (10k+ users)

---

## 🤖 AI-Assisted Development

This project is built with AI assistance (Claude, Cowork).

### **To make changes with Claude:**
```bash
# Make changes locally
git checkout -b feature/new-feature
# Claude makes changes via Cowork
git add .
git commit -m "Add new feature"
git push origin feature/new-feature

# Review & merge via GitHub
# Railway auto-deploys on merge to main
```

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🆘 Support

- **Email:** anandsingh8687@gmail.com
- **GitHub Issues:** https://github.com/anandsingh8687/dsa-case-os/issues

---

## 🙏 Acknowledgments

- **FastAPI** - Modern Python web framework
- **Moonshot AI** - LLM API for Kimi model
- **Railway** - Simplified cloud deployment
- **Claude (Anthropic)** - AI-assisted development

---

**Built with ❤️ using AI-assisted development**
