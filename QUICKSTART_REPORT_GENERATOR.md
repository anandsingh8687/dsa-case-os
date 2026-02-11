# Case Intelligence Report Generator - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Install Dependencies
```bash
cd backend
pip install reportlab pydantic fastapi
```

### Step 2: Verify Database Schema
Ensure the `case_reports` table exists:
```bash
psql -d dsa_case_os -f app/db/schema.sql
```

### Step 3: Test Report Generation
```bash
# Start the FastAPI server (if not running)
uvicorn app.main:app --reload --port 8000

# In another terminal, test the endpoint:
curl -X POST http://localhost:8000/api/v1/reports/case/CASE-20250210-0001/generate
```

---

## 📋 API Quick Reference

### Generate Report
```bash
curl -X POST http://localhost:8000/api/v1/reports/case/{case_id}/generate
```

**Returns:**
```json
{
  "status": "success",
  "case_id": "CASE-20250210-0001",
  "report_id": "uuid",
  "pdf_path": "/tmp/dsa_case_reports/CASE-20250210-0001_report.pdf",
  "lenders_matched": 5,
  "strengths_count": 7,
  "risks_count": 2
}
```

---

### Download PDF
```bash
curl -X GET http://localhost:8000/api/v1/reports/case/{case_id}/report/pdf \
     -o report.pdf
```

---

### Get WhatsApp Summary
```bash
curl -X GET http://localhost:8000/api/v1/reports/case/{case_id}/report/whatsapp
```

**Returns:**
```
📋 Case: CASE-20250210-0001

👤 Borrower: Rajesh Kumar | Proprietorship | 8.0yr

📊 CIBIL: 780 | Turnover: ₹120.0L | ABB: ₹5.0L

✅ Top Match: HDFC Bank - Business Loan (HIGH)

📈 5 lenders matched | Best score: 92/100
```

---

### Get Report Data (JSON)
```bash
curl -X GET http://localhost:8000/api/v1/reports/case/{case_id}/report
```

---

## 🧪 Quick Test

### Python Test Script
```python
import requests

# Generate report
response = requests.post(
    "http://localhost:8000/api/v1/reports/case/CASE-20250210-0001/generate"
)
print(response.json())

# Download PDF
pdf_response = requests.get(
    "http://localhost:8000/api/v1/reports/case/CASE-20250210-0001/report/pdf"
)
with open("test_report.pdf", "wb") as f:
    f.write(pdf_response.content)
print("✓ PDF saved to test_report.pdf")

# Get WhatsApp summary
summary = requests.get(
    "http://localhost:8000/api/v1/reports/case/CASE-20250210-0001/report/whatsapp"
)
print("\n" + summary.text)
```

---

## 🛠️ Common Tasks

### Task 1: Generate Report for a Case
```python
from app.services.stages.stage5_report import assemble_case_report
from app.services.stages.stage5_pdf_generator import generate_pdf_report
from uuid import UUID

# Get case UUID from case_id
case_uuid = UUID("...")  # Your case UUID

# Assemble report
report_data = await assemble_case_report(case_uuid)

# Generate PDF
pdf_bytes = generate_pdf_report(report_data)

# Save PDF
with open("report.pdf", "wb") as f:
    f.write(pdf_bytes)
```

---

### Task 2: Add Custom Strength Detection
Edit `backend/app/services/stages/stage5_report.py`:

```python
def compute_strengths(borrower, lender_matches):
    strengths = []

    # ... existing strength checks ...

    # ADD YOUR CUSTOM STRENGTH HERE:
    if borrower.your_custom_field > threshold:
        strengths.append("Your custom strength message")

    return strengths
```

---

### Task 3: Customize PDF Styling
Edit `backend/app/services/stages/stage5_pdf_generator.py`:

```python
def get_custom_styles():
    styles = getSampleStyleSheet()

    # Modify existing style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        fontSize=28,  # Increase from 24
        textColor=colors.HexColor('#YOUR_COLOR'),
        fontName='Helvetica-Bold'
    ))

    return styles
```

---

### Task 4: Change PDF Logo/Branding
Edit `backend/app/services/stages/stage5_pdf_generator.py > build_cover_page()`:

```python
def build_cover_page(report_data, styles):
    elements = []

    # Add your logo
    from reportlab.platypus import Image
    logo = Image('/path/to/logo.png', width=2*inch, height=1*inch)
    elements.append(logo)

    # ... rest of cover page ...
```

---

## 📊 Understanding the Report Structure

### CaseReportData Schema
```python
class CaseReportData(BaseModel):
    case_id: str                              # "CASE-20250210-0001"
    borrower_profile: BorrowerFeatureVector   # All borrower data
    checklist: DocumentChecklist              # Document status
    strengths: List[str]                      # ["Excellent credit score (780)", ...]
    risk_flags: List[str]                     # ["High cash deposit ratio (55%)", ...]
    lender_matches: List[EligibilityResult]   # Ranked lender list
    submission_strategy: str                  # Markdown-formatted strategy
    missing_data_advisory: List[str]          # ["CIBIL score not available", ...]
    expected_loan_range: Optional[str]        # "₹15.0L - ₹30.0L"
```

---

## 🔍 Debugging Tips

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check What Data is Available
```python
from app.services.stages.stage5_report import (
    load_borrower_features,
    load_eligibility_results
)

# Check borrower data
borrower = await load_borrower_features(case_uuid)
print(f"Feature completeness: {borrower.feature_completeness}%")

# Check lender matches
lenders = await load_eligibility_results(case_uuid)
print(f"Lenders evaluated: {len(lenders)}")
```

### Validate PDF Output
```bash
# Check if PDF is valid
file report.pdf
# Should output: "PDF document, version 1.4"

# Check PDF size
ls -lh report.pdf
# Should be > 50 KB for typical report
```

---

## 🎯 Integration with Frontend

### Example: React Component
```javascript
// Generate report button
const generateReport = async (caseId) => {
  const response = await fetch(
    `/api/v1/reports/case/${caseId}/generate`,
    { method: 'POST' }
  );
  const data = await response.json();

  if (data.status === 'success') {
    // Show success message
    alert(`Report generated! ${data.lenders_matched} lenders matched`);

    // Download PDF
    window.location.href = `/api/v1/reports/case/${caseId}/report/pdf`;
  }
};

// Get WhatsApp summary for sharing
const shareOnWhatsApp = async (caseId) => {
  const response = await fetch(
    `/api/v1/reports/case/${caseId}/report/whatsapp`
  );
  const summary = await response.text();

  // Copy to clipboard
  navigator.clipboard.writeText(summary);
  alert('Summary copied! Paste in WhatsApp');
};
```

---

## 📈 Performance Optimization

### Cache Reports
```python
# Add caching to avoid regenerating unchanged reports
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_report(case_id: str):
    # Check if report is recent and data hasn't changed
    # If so, return cached PDF
    pass
```

### Async PDF Generation
```python
# For high-volume scenarios, queue PDF generation
from celery import Celery

@celery.task
def generate_report_async(case_id):
    # Generate in background
    report_data = await assemble_case_report(case_uuid)
    pdf_bytes = generate_pdf_report(report_data)
    # Save and notify user
```

---

## 🚨 Error Handling

### Common Errors and Solutions

**Error:** `Case not found`
```python
# Solution: Verify case exists
SELECT * FROM cases WHERE case_id = 'CASE-20250210-0001';
```

**Error:** `No borrower features`
```python
# Solution: Run feature extraction first
POST /api/v1/features/case/{case_id}/extract
```

**Error:** `PDF generation failed`
```python
# Solution: Check ReportLab installation
pip install --upgrade reportlab
```

**Error:** `Storage key not found`
```python
# Solution: Ensure storage directory exists
mkdir -p /tmp/dsa_case_reports
chmod 755 /tmp/dsa_case_reports
```

---

## ✅ Pre-Deployment Checklist

- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Database schema up to date
- [ ] Storage directory created and writable
- [ ] Tests passing (`pytest tests/test_report.py`)
- [ ] API endpoints accessible
- [ ] PDF generation working
- [ ] WhatsApp summary formatting correct
- [ ] Error handling verified
- [ ] Logging configured
- [ ] Production storage (S3) configured

---

## 🎓 Next Steps

1. **Test with Real Data:** Run report generation on actual cases
2. **Customize Styling:** Adjust PDF colors, fonts, and layout
3. **Add Branding:** Include your logo and company details
4. **Integrate Frontend:** Connect to React/Vue UI
5. **Monitor Performance:** Track generation times and optimize
6. **User Feedback:** Collect DSA feedback and iterate

---

## 📚 Additional Resources

- **Full Documentation:** `REPORT_GENERATOR_IMPLEMENTATION.md`
- **Test Suite:** `backend/tests/test_report.py`
- **API Endpoints:** `backend/app/api/v1/endpoints/reports.py`
- **Report Service:** `backend/app/services/stages/stage5_report.py`
- **PDF Generator:** `backend/app/services/stages/stage5_pdf_generator.py`

---

**Happy Coding! 🎉**

For questions or issues, check the full implementation guide or run the test suite.
