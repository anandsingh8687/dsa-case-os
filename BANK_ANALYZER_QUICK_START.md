# Bank Statement Analyzer - Quick Start Guide

## 🎯 What It Does

Automatically analyzes bank statement PDFs to extract financial metrics for loan underwriting decisions.

## 📦 Files Created

```
backend/app/services/
├── credilo_parser.py              # Mock Credilo parser
└── stages/
    └── stage2_bank_analyzer.py    # Metrics computation engine

backend/app/api/v1/endpoints/
└── extraction.py                  # Updated with bank analysis integration

backend/tests/
└── test_bank_analyzer.py          # 20+ comprehensive tests
```

## 🚀 Quick Usage

### 1. Analyze Bank Statements (Standalone)

```python
from app.services.stages.stage2_bank_analyzer import get_analyzer

analyzer = get_analyzer()

# From PDF files
result = await analyzer.analyze([
    '/path/to/statement1.pdf',
    '/path/to/statement2.pdf'
])

print(f"Average Balance: ₹{result.avg_monthly_balance:,.2f}")
print(f"EMI Detected: ₹{result.emi_outflow_monthly:,.2f}")
print(f"Bounces: {result.bounce_count_12m}")
```

### 2. Via API Endpoint

```bash
# Upload bank statement PDFs to case
curl -X POST "http://localhost:8000/api/v1/cases/CASE-001/documents/upload" \
  -F "file=@hdfc_statement.pdf"

# Trigger extraction (includes bank analysis)
curl -X POST "http://localhost:8000/api/v1/extraction/case/CASE-001/extract" \
  -H "Authorization: Bearer <token>"
```

### 3. Access Results

```python
from app.services.stages.stage2_features import get_assembler

assembler = get_assembler()
features = await assembler.get_feature_vector(db, case_id="CASE-001")

# Bank metrics are now in the feature vector
print(features.avg_monthly_balance)
print(features.emi_outflow_monthly)
print(features.bounce_count_12m)
```

## 📊 Metrics Computed

| Metric | Description | Used For |
|--------|-------------|----------|
| `avg_monthly_balance` | Average of month-end balances | Lender min ABB requirements |
| `monthly_credit_avg` | Average monthly deposits | Income verification |
| `monthly_debit_avg` | Average monthly withdrawals | Expense pattern analysis |
| `emi_outflow_monthly` | Detected recurring EMIs | FOIR calculation |
| `bounce_count_12m` | Bounced transactions | Credit risk flag |
| `cash_deposit_ratio` | Cash deposits / Total credits | Money laundering risk |
| `peak_balance` | Maximum balance | Liquidity assessment |
| `min_balance` | Minimum balance | Cash flow health |
| `total_credits_12m` | Sum of all deposits | Annual turnover proxy |
| `total_debits_12m` | Sum of all withdrawals | Burn rate |
| `monthly_summary` | Per-month breakdown | Trend analysis |

## 🔍 Detection Logic

### EMI Detection
**Keywords:** `EMI`, `LOAN`, `NACH`, `ECS`, `SI-`, `MANDATE`, `BAJAJ`, `HDFC LOAN`, `TATA CAPITAL`

**Example transactions detected:**
- "NACH DEBIT FOR ICICI HOME LOAN EMI"
- "ECS SI- BAJAJ FINSERV AUTO LOAN"
- "STANDING INSTRUCTION CAR LOAN"

### Bounce Detection
**Keywords:** `BOUNCE`, `RETURN`, `DISHON`, `INSUFFICIENT`, `UNPAID`, `REJECT`, `CHQ RETURN`, `ECS RETURN`

**Example transactions detected:**
- "CHEQUE BOUNCE CHARGES"
- "ECS RETURN INSUFFICIENT FUNDS"
- "NACH RETURN DISHONOURED"

### Cash Deposit Detection
**Keywords:** `CASH DEP`, `BY CASH`, `CASH DEPOSIT`, `CASH CR`, `CASH CREDIT`
**Excludes:** `CASH CREDIT A/C` (account type)

**Example transactions detected:**
- "CASH DEPOSIT BY SELF" ✓
- "BY CASH CREDIT" ✓
- "TRANSFER FROM CASH CREDIT A/C" ✗ (excluded)

## 🧪 Testing

### Run Full Test Suite
```bash
cd backend
pytest tests/test_bank_analyzer.py -v
```

### Run Simple Test
```bash
python /sessions/great-brave-hypatia/test_bank_analyzer_simple.py
```

### Expected Output
```
✓ Transaction count: 8
✓ Avg monthly balance: ₹126,633.33
✓ EMI outflow monthly: ₹15,000.00
✓ Bounce count (12m): 1
✓ Confidence: 0.85
✅ ALL TESTS PASSED
```

## 🔧 Customization

### Add Custom EMI Keywords
Edit `backend/app/services/stages/stage2_bank_analyzer.py`:

```python
class BankStatementAnalyzer:
    EMI_KEYWORDS = [
        'EMI', 'LOAN', 'NACH',
        'YOUR_CUSTOM_KEYWORD',  # Add here
    ]
```

### Adjust Confidence Threshold
Edit `backend/app/services/stages/stage2_features.py`:

```python
assembler = FeatureAssembler(confidence_threshold=0.7)  # Default: 0.5
```

## 📝 Sample Data Structure

### Input (Credilo Parser Output)
```python
{
    'transactionDate': date(2024, 1, 5),
    'valueDate': date(2024, 1, 5),
    'narration': 'HDFC LOAN EMI',
    'chequeRefNo': '123456',
    'withdrawalAmt': 15000.0,
    'depositAmt': 0.0,
    'closingBalance': 110000.0,
}
```

### Output (BankAnalysisResult)
```python
BankAnalysisResult(
    bank_detected='HDFC',
    account_number='12345678901234',
    transaction_count=87,
    statement_period_months=12,
    avg_monthly_balance=125000.50,
    monthly_credit_avg=85000.00,
    emi_outflow_monthly=15000.00,
    bounce_count_12m=0,
    cash_deposit_ratio=0.12,
    confidence=0.87
)
```

## 🔗 Integration Points

1. **Stage 1 Classification** → Identifies BANK_STATEMENT documents
2. **Stage 2 Extraction** → Calls bank analyzer (this module)
3. **Stage 2 Features** → Assembles metrics into BorrowerFeatureVector
4. **Stage 4 Eligibility** → Uses metrics for hard filter checks
5. **Stage 5 Report** → Includes metrics in lender recommendations

## ⚠️ Production Checklist

- [ ] Replace mock Credilo parser with actual parser_engine.py
- [ ] Test with real bank statement PDFs from all 14 banks
- [ ] Validate metric calculations against manual calculations
- [ ] Set up monitoring for confidence scores
- [ ] Add caching for repeated analysis
- [ ] Configure keyword lists per bank/region
- [ ] Test with multi-account statements
- [ ] Add logging for failed transactions parsing

## 🆘 Troubleshooting

### Low Confidence Score
**Cause:** Poor PDF quality, incomplete data, short statement period
**Fix:** Request better quality PDFs, longer statement period (12 months ideal)

### No EMI Detected
**Cause:** Non-standard narration format
**Fix:** Add custom keywords to `EMI_KEYWORDS` list

### Zero Transactions Extracted
**Cause:** Bank format not supported by mock parser
**Fix:** Replace with actual Credilo parser

### High Cash Deposit Ratio
**Cause:** Many cash transactions or false positives
**Fix:** Review and refine `CASH_DEPOSIT_KEYWORDS` and `CASH_DEPOSIT_EXCLUDE` lists

## 📚 Additional Resources

- [Full Implementation Guide](./BANK_ANALYZER_IMPLEMENTATION.md)
- [BankAnalysisResult Schema](./backend/app/schemas/shared.py#L205)
- [BorrowerFeatureVector Schema](./backend/app/schemas/shared.py#L118)
- [Test Suite](./backend/tests/test_bank_analyzer.py)

---

**Need help?** Check the full implementation guide or run the test suite to see examples.
