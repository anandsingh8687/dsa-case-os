# Stage 0 Quick Start Guide

Get up and running with Stage 0 in 5 minutes!

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- pip

## 1. Install Dependencies (1 min)

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing
```

## 2. Setup Database (2 min)

```bash
# Create database
createdb dsa_case_os

# Run schema
psql dsa_case_os < app/db/schema.sql

# Or if using Alembic migrations
alembic upgrade head
```

## 3. Configure Environment (1 min)

Create `.env` file in `backend/`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os
LOCAL_STORAGE_PATH=./uploads
DEBUG=True
```

## 4. Start the Server (30 sec)

```bash
uvicorn app.main:app --reload --port 8000
```

Server should start at: http://localhost:8000

## 5. Test It! (30 sec)

### Option A: Use the Demo Script

```bash
python examples/stage0_demo.py
```

### Option B: Run Tests

```bash
pytest tests/test_stage0.py -v
```

### Option C: Manual API Test

```bash
# Create a case
curl -X POST http://localhost:8000/api/v1/cases/ \
  -H "Content-Type: application/json" \
  -d '{"borrower_name": "Test User"}'

# Response will include case_id like: "CASE-20240210-0001"

# Upload a file (create test.pdf first or use any PDF)
curl -X POST http://localhost:8000/api/v1/cases/CASE-20240210-0001/upload \
  -F "files=@test.pdf"
```

## Common Issues

### Database connection fails
- Check PostgreSQL is running: `pg_isready`
- Verify credentials in .env
- Test connection: `psql dsa_case_os`

### Import errors
- Ensure you're in the backend/ directory
- Check PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:$(pwd)"`
- Verify all packages installed: `pip list`

### Tests fail
- Create test database: `createdb dsa_case_os_test`
- Run schema on test DB: `psql dsa_case_os_test < app/db/schema.sql`

## What's Next?

1. ✅ Stage 0 is working
2. Next: Implement Stage 1 (Document Classification)
3. Read: `README_STAGE0.md` for full documentation
4. See: `STAGE0_IMPLEMENTATION_SUMMARY.md` for architecture details

## API Endpoints Quick Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/cases/` | Create case |
| POST | `/api/v1/cases/{id}/upload` | Upload files |
| GET | `/api/v1/cases/` | List cases |
| GET | `/api/v1/cases/{id}` | Get case |
| PATCH | `/api/v1/cases/{id}` | Update case |
| DELETE | `/api/v1/cases/{id}` | Delete case |

## Need Help?

- Read the full docs: `README_STAGE0.md`
- Check implementation details: `STAGE0_IMPLEMENTATION_SUMMARY.md`
- Run the demo: `python examples/stage0_demo.py`
- Review tests: `tests/test_stage0.py`

---

**You should now have a fully working Stage 0 implementation!** 🎉
