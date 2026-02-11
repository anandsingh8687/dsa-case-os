# DSA Copilot - Natural Language Lender Query Interface

## Overview

The DSA Copilot is a natural language interface for querying the lender knowledge base. DSAs can ask questions in plain English and get instant answers about lender policies, requirements, and eligibility criteria.

## Architecture

```
┌─────────────────┐
│  User Query     │  "lenders for 650 CIBIL"
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Stage 7 Retriever              │
│  - Query Classification         │
│  - Parameter Extraction         │
│  - Smart DB Queries             │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Lender Knowledge Base          │
│  - 25+ lenders                  │
│  - 21,000+ pincodes             │
│  - Real policy rules            │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Stage 7 Copilot                │
│  - Build Claude Prompt          │
│  - Call Claude API              │
│  - Format Response              │
│  - Log Query                    │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Natural Answer │  "Found 5 lenders: Bajaj, IIFL..."
└─────────────────┘
```

## Components

### 1. Query Classifier (`stage7_retriever.py`)

**Supported Query Types:**

| Query Type | Example | What It Does |
|------------|---------|--------------|
| **CIBIL** | "lenders for 650 CIBIL" | Finds lenders with min_cibil_score <= 650 |
| **Pincode** | "who serves 400001?" | Finds lenders serving that pincode |
| **Lender-Specific** | "Bajaj Finance policy" | Returns all products for that lender |
| **Comparison** | "compare Bajaj and IIFL" | Side-by-side comparison |
| **Vintage** | "1 year vintage accepted" | Finds lenders with min_vintage <= 1 |
| **Turnover** | "50 lakh turnover" | Finds lenders with min_turnover <= 50L |
| **Entity Type** | "proprietorship friendly" | Filters by eligible_entity_types |
| **Ticket Size** | "max ticket 50 lakh" | Finds lenders with max_ticket >= 50L |
| **Requirement** | "no video KYC" | Filters by verification requirements |
| **General** | "tell me about loans" | Overview of all lenders |

**Query Classification Logic:**

```python
def classify_query(query: str) -> Tuple[QueryType, Dict[str, Any]]:
    """
    Uses regex patterns to detect:
    - Numbers (CIBIL scores, pincodes, amounts)
    - Keywords (lender names, entity types, requirements)
    - Intent signals (compare, policy, requirement)

    Returns: (query_type, extracted_params)
    """
```

### 2. Data Retriever (`stage7_retriever.py`)

**Smart Database Queries:**

Each query type maps to an optimized SQL query:

```sql
-- CIBIL Query
SELECT l.lender_name, lp.product_name, lp.min_cibil_score, ...
FROM lender_products lp
INNER JOIN lenders l ON lp.lender_id = l.id
WHERE lp.min_cibil_score <= 650
ORDER BY lp.min_cibil_score ASC

-- Pincode Query
SELECT DISTINCT l.lender_name, lp.product_name, ...
FROM lender_pincodes lpc
INNER JOIN lenders l ON lpc.lender_id = l.id
INNER JOIN lender_products lp ON l.id = lp.lender_id
WHERE lpc.pincode = '400001'

-- Comparison Query
SELECT l.lender_name, lp.product_name, lp.min_cibil_score, ...
FROM lender_products lp
INNER JOIN lenders l ON lp.lender_id = l.id
WHERE LOWER(l.lender_name) LIKE LOWER('%bajaj%')
   OR LOWER(l.lender_name) LIKE LOWER('%iifl%')
```

### 3. Copilot Service (`stage7_copilot.py`)

**Flow:**

1. **Classify Query** → Extract intent and parameters
2. **Retrieve Data** → Fetch relevant lender records
3. **Build Prompt** → Format data for Claude
4. **Call Claude API** → Get natural language response
5. **Format Response** → Structure answer + sources
6. **Log Query** → Save to copilot_queries table

**Claude Prompt Template:**

```python
system_prompt = """
You are a helpful AI assistant for Business Loan DSAs in India.
Answer using ONLY the lender data provided.
Be specific: name lenders, quote exact numbers.
Use Indian terminology (Lakhs, CIBIL, FOIR).
Keep responses concise (2-4 sentences).
"""

user_prompt = f"""
Query Type: {query_type}
Parameters: {params}
Lenders Found: {count}

LENDER DATA:
{lender_data_json}

QUESTION: {user_query}
"""
```

**Fallback Mode:**

If Claude API is unavailable (no API key or error), the copilot uses a simple template-based response:

```python
"Found {count} lenders accepting CIBIL {score}.
Top matches: Bajaj Finance, IIFL, Lendingkart."
```

### 4. API Endpoint (`/api/v1/copilot/query`)

**Request:**
```json
POST /api/v1/copilot/query
{
  "query": "lenders for 650 CIBIL in Mumbai"
}
```

**Response:**
```json
{
  "answer": "Found 5 lenders accepting CIBIL 650 in Mumbai: Bajaj Finance (min CIBIL 650, max ticket ₹75L), IIFL (min CIBIL 675, max ticket ₹50L), Lendingkart (min CIBIL 650, max ticket ₹30L). All require 2+ years vintage and serve Mumbai pincodes.",

  "sources": [
    {
      "lender_name": "Bajaj Finance",
      "product_name": "BL",
      "min_cibil": 650,
      "min_vintage": "2y",
      "max_ticket": "₹75L",
      "pincode_coverage": 1500
    },
    ...
  ],

  "response_time_ms": 1250
}
```

## Example Queries

### CIBIL Queries
```
✓ "Which lenders accept CIBIL score below 650?"
✓ "lenders for 680 cibil"
✓ "credit score 700 minimum"
✓ "score above 750"
```

### Pincode Queries
```
✓ "who serves pincode 400001?"
✓ "lenders for Mumbai 400051"
✓ "pincode 110001 coverage"
```

### Lender-Specific Queries
```
✓ "What's the policy for Bajaj Finance?"
✓ "Tata Capital requirements"
✓ "Tell me about IIFL products"
```

### Comparison Queries
```
✓ "Compare Bajaj Finance and IIFL"
✓ "Bajaj vs Tata Capital vs Lendingkart"
```

### Business Vintage Queries
```
✓ "lenders accepting 1 year vintage"
✓ "2.5 years business experience"
✓ "new business loans"
```

### Turnover Queries
```
✓ "50 lakh annual turnover requirement"
✓ "minimum 1 crore revenue"
✓ "turnover of 75 lakh"
```

### Entity Type Queries
```
✓ "proprietorship friendly lenders"
✓ "private limited company loans"
✓ "partnership firm financing"
✓ "LLP loans"
```

### Requirement Queries
```
✓ "lenders with no video KYC"
✓ "without physical verification"
✓ "no field investigation required"
✓ "accept without GST"
```

## Database Schema

### copilot_queries (Logging)

```sql
CREATE TABLE copilot_queries (
    id              UUID PRIMARY KEY,
    user_id         UUID REFERENCES users(id),
    query_text      TEXT NOT NULL,
    response_text   TEXT,
    sources_used    JSONB,           -- {query_type, params, sources_count}
    response_time_ms INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

## Configuration

### Environment Variables

```bash
# Required for Claude API integration
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional: specify model
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Settings (`backend/app/core/config.py`)

```python
class Settings(BaseSettings):
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
```

## Testing

### Unit Tests

```bash
# Test query classification
pytest tests/test_copilot.py::TestQueryClassification

# Test data retrieval
pytest tests/test_copilot.py::TestDataRetrieval

# Test Claude integration
pytest tests/test_copilot.py::TestClaudeIntegration

# Test end-to-end
pytest tests/test_copilot.py::TestCopilotEndToEnd
```

### Manual Testing

```python
import asyncio
from app.services.stages.stage7_copilot import query_copilot

async def test():
    response = await query_copilot("lenders for 650 CIBIL")
    print(response.answer)
    print(response.sources)

asyncio.run(test())
```

## Performance

**Target Metrics:**
- Response time: < 2 seconds (with Claude API)
- Response time: < 500ms (fallback mode)
- Classification accuracy: > 95%
- Data retrieval: < 100ms

**Optimizations:**
- Indexed database queries (pincode, lender_name, min_cibil_score)
- Limit results to top 20 lenders
- Cache Claude API responses (future enhancement)
- Async/await throughout

## Future Enhancements

1. **Query History & Analytics**
   - Most common queries
   - Failed queries for improvement
   - User-specific query patterns

2. **Conversation Context**
   - Multi-turn conversations
   - "Tell me more about Bajaj"
   - "What about for proprietorship?"

3. **Smart Suggestions**
   - "Did you mean...?"
   - "You might also want to ask..."
   - Auto-complete queries

4. **Advanced Queries**
   - Combined filters: "CIBIL 650 + proprietorship + Mumbai"
   - Ranking: "best lenders for my profile"
   - Recommendations: "which lender should I try first?"

5. **Voice Interface**
   - Speech-to-text
   - Text-to-speech responses
   - WhatsApp integration

## Usage in DSA Workflow

### Quick Lender Lookup
```
DSA: "lenders for 680 CIBIL"
Copilot: "Found 8 lenders: Bajaj (650 min), IIFL (675), Tata Capital (700)..."
DSA: *immediately knows which lenders to approach*
```

### Client Eligibility Check
```
DSA: "proprietorship, 1.5 year vintage, 60 lakh turnover, pincode 400001"
Copilot: "3 lenders match: Lendingkart, Flexiloans, Indifi..."
DSA: *creates shortlist for case submission*
```

### Policy Verification
```
DSA: "Does Bajaj Finance require video KYC?"
Copilot: "Bajaj Finance BL product: video KYC required = Yes"
DSA: *prepares client accordingly*
```

## Troubleshooting

### Claude API Errors

**Problem:** `ANTHROPIC_API_KEY not configured`
**Solution:** Set environment variable or use fallback mode

**Problem:** `Rate limit exceeded`
**Solution:** Implement request throttling or use fallback

**Problem:** `API timeout`
**Solution:** Increase timeout or use fallback

### Database Errors

**Problem:** `No lenders found`
**Solution:** Check if knowledge base is populated

**Problem:** `Connection refused`
**Solution:** Verify PostgreSQL is running

### Classification Issues

**Problem:** Query classified as GENERAL instead of specific type
**Solution:** Check regex patterns, add more keywords

## Code Organization

```
backend/app/services/stages/
├── stage7_retriever.py    # Query classification & DB retrieval
├── stage7_copilot.py      # Claude integration & orchestration
└── COPILOT_README.md      # This file

backend/app/api/v1/endpoints/
└── copilot.py             # FastAPI endpoint

backend/tests/
└── test_copilot.py        # Comprehensive tests
```

## License & Credits

Built for DSA Case OS - Credit Intelligence Platform
Uses Anthropic Claude API for natural language generation
