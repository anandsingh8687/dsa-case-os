# Stage 3 Quick Start Guide

## What Was Built

A complete **Lender Knowledge Base** system that:
1. Ingests lender policy CSV (29 columns, 87 rows) into structured database
2. Ingests pincode serviceability CSV (28 lenders, 21K+ pincodes)
3. Provides REST APIs to query lenders, products, and pincode coverage
4. Serves as the data source for Stage 4 eligibility scoring engine

## Quick Start (3 Steps)

### Step 1: Place Your CSV Files

Ensure you have these files ready:
```
dsa-case-os/
├── Lender policy/
│   ├── Lender Policy.xlsx - BL Lender Policy.csv
│   └── Pincode list Lender Wise.csv
```

### Step 2: Run Ingestion

```bash
cd backend
python scripts/ingest_lender_data.py \
    --policy-csv "../Lender policy/Lender Policy.xlsx - BL Lender Policy.csv" \
    --pincode-csv "../Lender policy/Pincode list Lender Wise.csv"
```

**Expected Output:**
```
======================================================================
LENDER DATA INGESTION - FULL
======================================================================
...
Lenders created:  25
Products created: 87
Pincodes created: 21098
✓ Ingestion completed successfully
```

### Step 3: Verify Data

Start the server and query the API:

```bash
# Start FastAPI server
uvicorn app.main:app --reload

# In another terminal:
# Get all lenders
curl http://localhost:8000/api/v1/lenders/

# Get knowledge base stats
curl http://localhost:8000/api/v1/lenders/stats

# Find lenders by pincode (Delhi)
curl http://localhost:8000/api/v1/lenders/by-pincode/110001
```

## Key API Endpoints

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `GET /lenders/` | List all lenders | `curl /lenders/` |
| `GET /lenders/{id}/products` | Get lender's products | `curl /lenders/{uuid}/products` |
| `GET /lenders/by-pincode/{pin}` | Find lenders by pincode | `curl /lenders/by-pincode/110001` |
| `GET /lenders/products/all` | Get all products (for Stage 4) | `curl /lenders/products/all?program_type=banking` |
| `GET /lenders/stats` | Knowledge base stats | `curl /lenders/stats` |
| `POST /lenders/ingest/policy` | Upload policy CSV | `curl -F file=@policy.csv /lenders/ingest/policy` |

## Key Python Functions

### Ingestion
```python
from app.services.stages.stage3_ingestion import ingest_all_lender_data

stats = await ingest_all_lender_data(
    policy_csv_path="path/to/policy.csv",
    pincode_csv_path="path/to/pincodes.csv"
)
```

### Queries
```python
from app.services import lender_service

# List all lenders
lenders = await lender_service.list_lenders(active_only=True)

# Get products for eligibility engine (Stage 4)
products = await lender_service.get_all_products_for_scoring(
    program_type="banking",
    active_only=True
)

# Find lenders by pincode
lenders = await lender_service.find_lenders_by_pincode("110001")

# Check pincode coverage
coverage = await lender_service.check_pincode_coverage("110001")
# Returns: {pincode, serviced, lender_count, lender_names}
```

## Data Model

**Lender → Products → Pincodes**

```
Lender: Indifi
├── Product: BL
│   ├── Min CIBIL: 650
│   ├── Min Vintage: 2 years
│   ├── Min Turnover: 24L
│   ├── Max Ticket: 30L
│   ├── Entities: [pvt_ltd, llp, proprietorship]
│   └── ...29 other criteria fields
└── Pincodes: [110001, 110002, ..., 560001] (15,000+)
```

## CSV Format Examples

### Lender Policy CSV
```csv
Lender,Product Program,Min. Vintage,Min. Score,Min. Turnover,Max Ticket size,...
Indifi,BL,2,650,24L,30L,...
Bajaj,STBL,2,700,36L,50L,...
```

### Pincode CSV (unusual column-based format)
```csv
GODREJ,LENDINGKART,INDIFI,BAJAJ,...
110001,110001,110001,110001,...
110002,110002,110002,110002,...
```

## Field Parsing Examples

The system intelligently parses complex field formats:

| Input | Parsed Value | Field |
|-------|-------------|-------|
| `"30L"` | `30.0` | Max Ticket size (Lakhs) |
| `">=25k"` | `0.25` | ABB (in Lakhs) |
| `"2 years"` | `2.0` | Min Vintage |
| `"22-65"` | `age_min=22, age_max=65` | Age range |
| `"Pvt Ltd, LLP"` | `["pvt_ltd", "llp"]` | Entity types |
| `"6 months"` | `6` | Banking statement months |
| `"Mandatory"` | `True` | GST required |
| `"NA"` | `False` | Video KYC |
| `"Policy not available"` | `policy_available=False` | Status flag |

## Troubleshooting

### Problem: "Lender not found" errors during pincode ingestion
**Solution:** Run policy CSV ingestion first - pincodes require lenders to exist

### Problem: Some pincodes skipped
**Reason:** Non-numeric values (city names) in the pincode CSV are automatically skipped

### Problem: Import errors
**Solution:** Install dependencies:
```bash
pip install fastapi sqlalchemy asyncpg pydantic
```

## Files Overview

```
backend/
├── app/
│   ├── services/
│   │   ├── stages/stage3_ingestion.py  ← CSV parsers and ingestion logic
│   │   └── lender_service.py           ← CRUD and query functions
│   ├── api/v1/endpoints/
│   │   └── lenders.py                  ← REST API endpoints
│   └── schemas/shared.py               ← LenderProductRule schema
├── scripts/
│   └── ingest_lender_data.py           ← CLI ingestion tool
└── tests/
    └── test_knowledge_base.py          ← Unit tests

Total: ~2,000 lines of code
```

## Next Steps

1. ✅ **Data Ingestion**: Run the ingestion script with your CSV files
2. ✅ **Verification**: Query the APIs to verify data loaded correctly
3. 🔲 **Stage 4**: Build eligibility engine that uses `get_all_products_for_scoring()`
4. 🔲 **Stage 5**: Generate reports with lender recommendations
5. 🔲 **Stage 6**: Create WhatsApp-ready output with top lenders

## Sample Query Results

### Get Lender Stats
```bash
curl http://localhost:8000/api/v1/lenders/stats
```
```json
{
    "lenders": {"total": 28, "active": 25},
    "products": {"total": 87, "active": 84, "no_policy": 3},
    "pincodes": {"unique_covered": 21098},
    "program_types": {
        "banking": 22,
        "income": 8,
        "hybrid": 54
    }
}
```

### Find Lenders by Pincode
```bash
curl http://localhost:8000/api/v1/lenders/by-pincode/110001
```
```json
{
    "pincode": "110001",
    "lender_count": 15,
    "lenders": [
        {
            "lender_id": "uuid-1",
            "lender_name": "Indifi",
            "lender_code": "INDIFI",
            "product_count": 2
        },
        {
            "lender_id": "uuid-2",
            "lender_name": "Bajaj",
            "lender_code": "BAJAJ",
            "product_count": 3
        }
    ]
}
```

---

**Status**: ✅ Complete - Ready for CSV ingestion and Stage 4 integration

**Questions?** See `STAGE3_KNOWLEDGE_BASE.md` for detailed documentation.
