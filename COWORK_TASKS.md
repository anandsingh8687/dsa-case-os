# Claude Cowork Tasks - Phase 2 Enhancements

## 🎯 Overview
All tasks are independent and can run in parallel batches. Each task has complete context.

---

## 📦 BATCH 1: Core Data Extraction & APIs (High Priority)
*These tasks extract and process data. Run all 3 in parallel.*

---

### **TASK 1: GST API Integration & Auto-fill**

**Context:**
We have a GST API that returns company details when given a GSTIN. We need to extract GSTIN from uploaded documents, call the API, and use the response to pre-fill the case form.

**GST API Details:**
- Endpoint: `https://taxpayer.irisgst.com/api/search?gstin={gstin}`
- API Key: `1719e93b-14c9-48a0-8349-cd89dc3b5311`
- Header: `apikey: {API_KEY}`
- Timeout: 30 seconds

**Response Format:**
```json
{
  "status_code": 1,
  "gstin": "22BTTPR3963C1ZF",
  "name": "CHOKKAPU MAHESWARA RAO",
  "tradename": "LAKSHMI TRADERS",
  "registrationDate": "2024-04-04",
  "constitution": "Sole Proprietorship",
  "pradr": {
    "pncd": "494001",
    "stcd": "Chhattisgarh"
  }
}
```

**What to Extract and Map:**
- `tradename` → borrower_name (if tradename is empty, use `name`)
- `constitution` → entity_type (map to our EntityType enum)
- `registrationDate` → calculate business_vintage_years
- `pradr.pncd` → pincode
- `pradr.stcd` → state
- `status` → track if GST is active

**Tasks:**

1. **Create GST API Service** (`backend/app/services/gst_api.py`):
```python
class GSTAPIService:
    API_URL = "https://taxpayer.irisgst.com/api/search?gstin={gstin}"
    API_KEY = "1719e93b-14c9-48a0-8349-cd89dc3b5311"

    async def fetch_company_details(self, gstin: str) -> dict:
        """Fetch company details from GST API"""
        # Call API, handle errors, return parsed data
```

2. **Extract GSTIN from Documents** (`backend/app/services/stages/stage0_case_entry.py`):
   - After OCR, search for GSTIN pattern: `\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}`
   - Find in GST returns, GST certificates
   - Save GSTIN to case metadata

3. **Auto-trigger GST API** (`backend/app/services/stages/stage0_case_entry.py`):
   - When GSTIN detected, call GST API automatically
   - Save response to `case.gst_data` (JSONB field)
   - Calculate business vintage: `(today - registrationDate).years`

4. **Add API Endpoint** (`backend/app/api/v1/endpoints/cases.py`):
```python
@router.get("/cases/{case_id}/gst-data")
async def get_gst_data(case_id: str):
    """Get extracted GST data for a case"""
    # Return gst_data from case if available
```

5. **Add Database Field** (`backend/app/db/schema.sql`):
```sql
ALTER TABLE cases ADD COLUMN gst_data JSONB;
ALTER TABLE cases ADD COLUMN gstin VARCHAR(15);
```

**Testing:**
- Upload GST return PDF
- Check logs for GSTIN extraction
- Verify GST API call
- Verify data saved to database

**Deliverable:**
- GST API integrated
- GSTIN auto-extracted from documents
- Company data auto-populated

---

### **TASK 2: Monthly Turnover from Bank Statements**

**Context:**
Currently, bank statement analysis extracts monthly credits. We need to calculate **Monthly Turnover** = Average of all monthly credit totals.

**Current State:**
- `stage2_bank_analyzer.py` already has `monthly_credit_avg`
- We need to save this as `monthly_turnover` in the feature vector

**Task:**

1. **Update Feature Extraction** (`backend/app/services/stages/stage2_extraction.py`):
   - When bank analysis returns `monthly_credit_avg`, save it as TWO fields:
     - `monthly_credit_avg` (existing)
     - `monthly_turnover` (new) = `monthly_credit_avg`

2. **Add to Schema** (`backend/app/schemas/shared.py`):
```python
class BorrowerFeatureVector(BaseModel):
    # ... existing fields ...
    monthly_turnover: Optional[float] = None  # in Rupees, average monthly credits
```

3. **Update Database** (`backend/app/db/schema.sql`):
```sql
ALTER TABLE borrower_features ADD COLUMN monthly_turnover FLOAT;
```

4. **Display in Frontend** (static HTML `index.html`):
   - Add "Monthly Turnover" row in Financial section of Profile tab
   - Format: `₹{monthly_turnover.toLocaleString('en-IN')}`

**Testing:**
- Upload bank statements
- Run extraction
- Verify `monthly_turnover` appears in Profile tab

**Deliverable:**
- Monthly turnover calculated and displayed
- Available for manual override

---

### **TASK 3: Business Vintage Auto-calculation**

**Context:**
When GST registration date is extracted, automatically calculate business vintage in years.

**Formula:**
```python
from datetime import date

registration_date = date.fromisoformat(gst_data['registrationDate'])
today = date.today()
vintage_years = (today - registration_date).days / 365.25
```

**Task:**

1. **Update GST API Service** (`backend/app/services/gst_api.py`):
   - Parse `registrationDate` from API response
   - Calculate `business_vintage_years`
   - Return in response

2. **Save to Feature Vector** (`backend/app/services/stages/stage2_features.py`):
   - When GST data available, use calculated vintage
   - If no GST data, leave blank for manual entry

3. **Show in Frontend** (static HTML):
   - Profile tab: Display vintage with "(from GST)" indicator
   - Manual Override: Pre-fill but allow editing

**Testing:**
- Upload GST document
- Check Profile tab shows vintage
- Verify calculation is correct

**Deliverable:**
- Business vintage auto-calculated from GST
- Editable in manual override

---

## 📦 BATCH 2: Frontend Enhancements (Medium Priority)
*These improve the UI/UX. Run all 3 in parallel.*

---

### **TASK 4: Smart Form Pre-fill UI**

**Context:**
After GST data is extracted, the New Case form should be pre-filled automatically.

**Requirements:**
1. Check if case has GST data before showing form
2. Pre-populate: borrower_name, entity_type, pincode
3. Show indicator: "(Auto-filled from GST)" for pre-filled fields
4. Allow user to edit pre-filled fields
5. User only manually fills: program_type, loan_amount_requested

**Implementation:**

**File:** `frontend/src/pages/NewCase.jsx` (React version)

```javascript
const NewCase = () => {
  const [gstData, setGstData] = useState(null);

  useEffect(() => {
    // Check if we have GST data for this case
    const checkGSTData = async () => {
      const response = await api.get(`/cases/${caseId}/gst-data`);
      if (response.data) {
        setGstData(response.data);
        // Pre-fill form
        setValue('borrower_name', response.data.tradename || response.data.name);
        setValue('entity_type', response.data.entity_type);
        setValue('pincode', response.data.pincode);
      }
    };
    checkGSTData();
  }, [caseId]);

  return (
    <form>
      <Input
        label="Borrower Name"
        {...register('borrower_name')}
        helperText={gstData ? "✓ Auto-filled from GST" : ""}
      />
      {/* Similar for other fields */}
    </form>
  );
};
```

**File:** `backend/app/static/index.html` (Static HTML version - PRIORITY)

```javascript
// In Alpine.js app data
gstData: null,

// When opening New Case
async checkGSTData(caseId) {
  const data = await this.api('GET', '/cases/'+caseId+'/gst-data');
  this.gstData = data;
  // Pre-fill form fields
  if (data) {
    this.caseForm.borrower_name = data.tradename || data.name;
    this.caseForm.entity_type = data.entity_type;
    this.caseForm.pincode = data.pincode;
  }
}
```

**Testing:**
- Upload GST document
- Go to case
- Check form is pre-filled
- Verify green checkmark appears

**Deliverable:**
- Form auto-fills with GST data
- Clear visual indicator
- User can still edit

---

### **TASK 5: Enhanced Profile Tab Display**

**Context:**
Profile tab currently shows 4 sections. We need to add more parameters and improve layout.

**New Parameters to Add:**
- Monthly Turnover (from bank statements)
- Business Vintage (from GST or manual)
- GST Status (Active/Inactive)
- State (from GST address)

**Improved Layout:**
```
┌─────────────────────────────────────────┐
│ IDENTITY            BUSINESS            │
│ Name: ...          Entity: ...          │
│ PAN: ...           Vintage: 5 yrs ✓GST  │
│ DOB: ...           GSTIN: ...           │
│                    Pincode: ...         │
│                    State: ...           │
│                    Status: Active       │
│                                         │
│ FINANCIAL           CREDIT              │
│ Annual TO: ...     CIBIL: 740          │
│ Monthly TO: ₹5L    Active Loans: 2     │
│ Avg Balance: ₹2L   Overdues: 0         │
│ Monthly Credits:   Enquiries: 1        │
│ Bounces: 0                              │
└─────────────────────────────────────────┘
```

**File:** `backend/app/static/index.html`

**Task:**
1. Add new fields to Profile tab display
2. Show "(from GST)" indicator for auto-filled data
3. Color code: Green for good values, Red for concerns
4. Responsive grid layout

**Code Changes:**
```html
<!-- Add to Business section -->
<div class="flex justify-between text-sm">
  <span class="text-gray-500">State</span>
  <span class="font-medium" x-text="features.state||'—'"></span>
</div>
<div class="flex justify-between text-sm">
  <span class="text-gray-500">GST Status</span>
  <span :class="features.gst_status==='Active'?'text-emerald-600':'text-red-600'"
        x-text="features.gst_status||'—'"></span>
</div>

<!-- Add to Financial section -->
<div class="flex justify-between text-sm">
  <span class="text-gray-500">Monthly Turnover</span>
  <span class="font-medium" x-text="features.monthly_turnover?'₹'+Number(features.monthly_turnover).toLocaleString('en-IN'):'—'"></span>
</div>
```

**Testing:**
- Open Profile tab
- Verify all new fields appear
- Check color coding works
- Test responsive layout

**Deliverable:**
- Enhanced Profile display
- More financial metrics visible
- Professional appearance

---

### **TASK 6: Eligibility Analysis Explanation UI**

**Context:**
When lenders don't match, users don't know why. We need to show detailed explanation.

**Requirements:**
1. When 0 lenders match, show "Why No Matches?" section
2. List failed criteria:
   - "CIBIL below minimum (650 vs 700 required)"
   - "Business vintage too low (2 years vs 3 required)"
   - "Average balance insufficient (₹50k vs ₹1L required)"
3. Show suggestions:
   - "Improve CIBIL score to 700+"
   - "Wait 1 more year to meet vintage requirement"
   - "Increase average bank balance"

**File:** `backend/app/static/index.html`

**Implementation:**
```html
<!-- Add to Eligibility Tab -->
<template x-if="eligibility && eligibility.lenders_passed === 0">
  <div class="bg-red-50 border border-red-200 rounded-xl p-6">
    <h4 class="font-semibold text-red-800 mb-3">Why No Lenders Matched</h4>

    <div class="space-y-2 mb-4">
      <template x-for="reason in eligibility.rejection_reasons" :key="reason">
        <div class="flex items-start gap-2">
          <span class="text-red-600">✗</span>
          <span class="text-sm text-red-700" x-text="reason"></span>
        </div>
      </template>
    </div>

    <h5 class="font-semibold text-gray-700 mb-2">Suggested Actions:</h5>
    <div class="space-y-1">
      <template x-for="action in eligibility.suggested_actions" :key="action">
        <div class="flex items-start gap-2">
          <span class="text-blue-600">→</span>
          <span class="text-sm text-gray-600" x-text="action"></span>
        </div>
      </template>
    </div>
  </div>
</template>
```

**Backend Changes:**
`backend/app/services/stages/stage4_eligibility.py`:

```python
def generate_rejection_analysis(feature_vector, lender_policies):
    """Analyze why lenders rejected and suggest improvements"""
    reasons = []
    actions = []

    for policy in lender_policies:
        if feature_vector.cibil_score < policy.min_cibil_score:
            reasons.append(f"{policy.lender_name}: CIBIL {feature_vector.cibil_score} < {policy.min_cibil_score} required")
            actions.append(f"Improve CIBIL to {policy.min_cibil_score}+ for {policy.lender_name}")

        # Similar for other criteria

    return {
        'rejection_reasons': reasons,
        'suggested_actions': actions
    }
```

**Testing:**
- Create case with low CIBIL (e.g., 600)
- Run eligibility
- Verify explanation shows
- Check suggestions are helpful

**Deliverable:**
- Clear explanation when no lenders match
- Actionable suggestions
- User understands what to improve

---

## 📦 BATCH 3: Communication & Copilot (High Priority)
*These improve user communication and AI responses. Run both in parallel.*

---

### **TASK 7: Lender Copilot - Show ALL Results**

**Context:**
Currently, copilot only shows 4-5 lenders when query asks for all. We need to show COMPLETE results.

**Problem:**
Query: "Which lenders fund below 650 CIBIL?"
Current: Shows 4 lenders
Expected: Shows ALL 15 matching lenders

**Root Cause:**
1. Database query limits results (LIMIT 10)
2. LLM truncates response
3. Retrieval doesn't return all matches

**File:** `backend/app/services/stages/stage7_copilot.py`

**Fixes:**

1. **Remove query limits:**
```python
# BEFORE (wrong):
results = await db.fetch("SELECT ... LIMIT 10")

# AFTER (correct):
results = await db.fetch("SELECT ...")  # Get ALL results
```

2. **Format ALL results in prompt:**
```python
# Build complete context
all_lenders = "\n".join([
    f"- {r['lender_name']} - {r['product_name']} (CIBIL min: {r['min_cibil_score']})"
    for r in results
])

prompt = f"""
Based on the lender policies, answer this query: {query}

Available lenders ({len(results)} total):
{all_lenders}

IMPORTANT: List ALL matching lenders, not just a few. Be comprehensive.
"""
```

3. **Validate response completeness:**
```python
# After LLM response, check if all lenders mentioned
mentioned_lenders = extract_lender_names(llm_response)
if len(mentioned_lenders) < len(results) * 0.8:  # If <80% mentioned
    # Append summary
    llm_response += f"\n\nComplete list: {', '.join([r['lender_name'] for r in results])}"
```

**Testing:**
- Ask: "Which lenders accept CIBIL below 650?"
- Verify response lists ALL matching lenders
- Check no truncation

**Deliverable:**
- Copilot shows complete results
- No information loss
- Users get full picture

---

### **TASK 8: WhatsApp Case Chat Integration**

**Context:**
DSAs need to communicate with customers about missing documents. We need a WhatsApp integration tied to each case.

**Requirements:**
1. Each case can have a linked phone number
2. User scans QR code to link their WhatsApp
3. All messages for that case go through linked number
4. Persistent across sessions (re-scan if expired)

**Architecture:**
```
Case → Phone Number → WhatsApp Session → QR Code
```

**Implementation:**

**Backend:**

1. **Add phone number to cases** (`backend/app/db/schema.sql`):
```sql
ALTER TABLE cases ADD COLUMN customer_phone VARCHAR(20);
ALTER TABLE cases ADD COLUMN whatsapp_session_id VARCHAR(100);
ALTER TABLE cases ADD COLUMN whatsapp_qr_code TEXT;
ALTER TABLE cases ADD COLUMN whatsapp_linked_at TIMESTAMPTZ;
```

2. **WhatsApp Service** (`backend/app/services/whatsapp_service.py`):
```python
class WhatsAppService:
    def generate_qr_code(self, case_id: str) -> str:
        """Generate QR code for WhatsApp Web linking"""
        # Use whatsapp-web.js or similar
        # Return QR code data URL

    async def send_message(self, phone: str, message: str):
        """Send WhatsApp message"""
        # Use WhatsApp Business API or Web API

    def is_session_active(self, session_id: str) -> bool:
        """Check if WhatsApp session is still active"""
```

3. **API Endpoints** (`backend/app/api/v1/endpoints/whatsapp.py`):
```python
@router.post("/cases/{case_id}/whatsapp/link")
async def link_whatsapp(case_id: str, phone: str):
    """Link phone number to case"""
    # Generate QR code
    # Save to case
    # Return QR code

@router.post("/cases/{case_id}/whatsapp/send")
async def send_whatsapp_message(case_id: str, message: str):
    """Send message via linked WhatsApp"""
    # Get phone from case
    # Send message
```

**Frontend** (`backend/app/static/index.html`):

```html
<!-- Add to Checklist tab -->
<div class="bg-white rounded-xl border p-4">
  <h4 class="font-semibold mb-3">Customer Communication</h4>

  <template x-if="!currentCase.whatsapp_linked_at">
    <div>
      <p class="text-sm text-gray-600 mb-3">Link WhatsApp to send document requests</p>
      <button @click="linkWhatsApp()" class="btn btn-primary">
        📱 Link WhatsApp
      </button>
    </div>
  </template>

  <template x-if="currentCase.whatsapp_linked_at">
    <div>
      <p class="text-sm text-emerald-600 mb-2">
        ✓ WhatsApp linked: {currentCase.customer_phone}
      </p>
      <button @click="sendWhatsAppMessage()" class="btn btn-secondary">
        💬 Send Message
      </button>
    </div>
  </template>
</div>

<!-- QR Code Modal -->
<div x-show="showWhatsAppQR" class="modal">
  <div class="modal-content">
    <h3>Scan to Link WhatsApp</h3>
    <img :src="whatsappQR" alt="WhatsApp QR Code" />
    <p class="text-sm text-gray-600">
      Scan this code with your WhatsApp to link this case
    </p>
  </div>
</div>
```

**Testing:**
1. Open case
2. Click "Link WhatsApp"
3. Scan QR with phone
4. Send test message
5. Verify message delivered

**Deliverable:**
- WhatsApp per-case integration
- QR code linking
- Message sending works

---

## 📦 BATCH 4: Report Improvements (Medium Priority)
*These enhance reporting. Run both in parallel.*

---

### **TASK 9: LLM-Based Report Generation**

**Context:**
Current reports use bullet points. Need professional narrative paragraphs.

**Current:**
```
**Primary Target:** Tata Capital - Digital
- Eligibility Score: 85/100
- Approval Probability: HIGH
```

**Desired:**
```
Based on comprehensive analysis of the borrower's financial profile and business
credentials, we recommend approaching Tata Capital's Digital Business Loan product
as the primary target. This recommendation is supported by a strong eligibility
score of 85/100, indicating high alignment between the borrower's profile and
the lender's requirements...
```

**File:** `backend/app/services/stages/stage5_report.py`

**Implementation:**

1. **Create LLM narrative generator:**
```python
async def generate_submission_strategy_narrative(
    eligibility_results,
    feature_vector,
    top_lender
) -> str:
    """Generate professional narrative using Claude API"""

    prompt = f"""
    You are a professional lending analyst writing a submission strategy report.

    Borrower Profile:
    - Name: {feature_vector.full_name}
    - Business: {feature_vector.business_vintage_years} years old
    - CIBIL Score: {feature_vector.cibil_score}
    - Average Balance: ₹{feature_vector.avg_monthly_balance}
    - Monthly Credits: ₹{feature_vector.monthly_credit_avg}

    Top Matching Lender:
    - Lender: {top_lender.lender_name}
    - Product: {top_lender.product_name}
    - Eligibility Score: {top_lender.eligibility_score}/100
    - Approval Probability: {top_lender.approval_probability}
    - Expected Ticket: ₹{top_lender.expected_ticket_min}L - ₹{top_lender.expected_ticket_max}L

    Other Strong Matches: {backup_lenders}

    Write a professional 3-4 paragraph submission strategy that:
    1. Explains why the primary lender is recommended
    2. Highlights borrower's strengths
    3. Suggests document preparation steps
    4. Mentions backup options

    Use clear, professional language. Write in narrative format, not bullet points.
    """

    # Call Claude API
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.CLAUDE_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text
```

2. **Replace bullet strategy:**
```python
# BEFORE:
submission_strategy = generate_bullet_strategy(...)

# AFTER:
submission_strategy = await generate_submission_strategy_narrative(...)
```

**Testing:**
- Generate report
- Check submission strategy is narrative
- Verify professional tone
- No bullet points

**Deliverable:**
- LLM-generated narrative report
- Professional tone
- Easy to read

---

### **TASK 10: WhatsApp Direct Share**

**Context:**
Reports have "Copy Text" button. Need direct WhatsApp share.

**Requirements:**
1. Replace "Copy Text" with "Share via WhatsApp"
2. Show modal with phone number input
3. Generate WhatsApp share link
4. Open WhatsApp with pre-filled message

**File:** `backend/app/static/index.html`

**Implementation:**

```html
<!-- Replace Copy button -->
<button @click="shareViaWhatsApp()" class="btn btn-success">
  📱 Share via WhatsApp
</button>

<!-- WhatsApp Share Modal -->
<div x-show="showWhatsAppShareModal" class="modal">
  <div class="modal-content">
    <h3>Share via WhatsApp</h3>
    <input
      type="tel"
      placeholder="Enter phone number (with country code)"
      x-model="whatsappSharePhone"
      class="input"
    />
    <p class="text-xs text-gray-500">Example: +919876543210</p>

    <div class="flex gap-3 mt-4">
      <button @click="sendToWhatsApp()" class="btn btn-primary">
        Send Message
      </button>
      <button @click="generateWhatsAppQR()" class="btn btn-secondary">
        Show QR Code
      </button>
    </div>

    <!-- QR Code display -->
    <div x-show="whatsappShareQR" class="mt-4">
      <img :src="whatsappShareQR" alt="WhatsApp QR" />
      <p class="text-sm">Scan to open on your phone</p>
    </div>
  </div>
</div>
```

**JavaScript:**
```javascript
shareViaWhatsApp() {
  this.showWhatsAppShareModal = true;
},

sendToWhatsApp() {
  const phone = this.whatsappSharePhone.replace(/\D/g, '');
  const message = this.formatReportForWhatsApp(this.currentReport);
  const encoded = encodeURIComponent(message);
  const url = `https://wa.me/${phone}?text=${encoded}`;
  window.open(url, '_blank');
  this.showWhatsAppShareModal = false;
},

formatReportForWhatsApp(report) {
  return `
*Case Intelligence Report*
Case: ${report.case_id}
Borrower: ${report.borrower_name}

*Recommendation:*
${report.submission_strategy}

*Top Lenders:*
${report.top_lenders.map(l => `- ${l.name}`).join('\n')}

Generated by DSA Case OS
  `.trim();
}
```

**Testing:**
- Generate report
- Click "Share via WhatsApp"
- Enter phone number
- Verify WhatsApp opens with message
- Test QR code option

**Deliverable:**
- Direct WhatsApp sharing
- QR code option
- Clean message formatting

---

## 📦 BATCH 5: Advanced Features (Lower Priority)
*These are nice-to-have enhancements. Run when Batches 1-4 complete.*

---

### **TASK 11: Flexible Upload Flow**

**Context:**
Allow users to upload documents BEFORE filling form. Extract data, then show pre-filled form.

**UI Flow:**
```
New Case → Choose Mode
  ├─ "Start with Documents" → Upload → Extract → Show pre-filled form
  └─ "Fill Details First" → Form → Upload → Process
```

**File:** `backend/app/static/index.html`

**Implementation:**
```html
<div class="new-case-mode-selector">
  <h2>Create New Case</h2>
  <div class="mode-cards">
    <div @click="startMode='documents'" class="mode-card">
      <h3>📄 Start with Documents</h3>
      <p>Upload documents first, we'll extract details</p>
    </div>
    <div @click="startMode='manual'" class="mode-card">
      <h3>📝 Fill Details First</h3>
      <p>Provide information, then upload documents</p>
    </div>
  </div>
</div>

<template x-if="startMode==='documents'">
  <!-- Show upload dropzone -->
  <!-- After upload, extract GST, show pre-filled form -->
</template>

<template x-if="startMode==='manual'">
  <!-- Show form first (current flow) -->
</template>
```

**Testing:**
- Test both modes
- Verify documents-first extracts data
- Verify manual mode works as before

**Deliverable:**
- Two entry modes
- Flexible workflow
- User choice

---

### **TASK 12: Bank Statement ZIP & Analysis**

**Context:**
All bank statement PDFs should be zipped and sent to Credilo analyzer in one batch.

**Requirements:**
1. Identify all documents classified as "bank_statement"
2. Create ZIP file with all bank PDFs
3. Send ZIP to Credilo analyzer
4. Parse comprehensive response
5. Calculate monthly turnover from all statements combined

**File:** `backend/app/services/stages/stage2_bank_analyzer.py`

**Implementation:**
```python
async def analyze_bank_statements_batch(self, case_id: str) -> BankAnalysisResult:
    """Analyze all bank statements for a case as a batch"""

    # 1. Get all bank statement documents
    bank_docs = await db.fetch("""
        SELECT id, storage_key, original_filename
        FROM documents
        WHERE case_id = $1 AND doc_type = 'bank_statement'
    """, case_id)

    # 2. Create temporary ZIP
    import zipfile
    import tempfile

    zip_path = tempfile.mktemp(suffix='.zip')
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for doc in bank_docs:
            pdf_path = storage.get_file_path(doc['storage_key'])
            zf.write(pdf_path, doc['original_filename'])

    # 3. Send ZIP to Credilo analyzer
    credilo_result = await self.credilo_parser.parse_zip(zip_path)

    # 4. Calculate monthly turnover
    all_transactions = credilo_result.transactions
    monthly_credits = self._group_credits_by_month(all_transactions)
    monthly_turnover = sum(monthly_credits.values()) / len(monthly_credits)

    return BankAnalysisResult(
        monthly_turnover=monthly_turnover,
        avg_monthly_balance=credilo_result.avg_balance,
        # ... other fields
    )
```

**Testing:**
- Upload 3+ bank statement PDFs
- Run extraction
- Verify ZIP created
- Check monthly turnover calculated from all statements

**Deliverable:**
- Batch bank analysis
- More accurate turnover
- ZIP automation

---

## 🎯 Execution Plan

### **Week 1: Core Features**
Run **Batch 1** + **Task 7** in parallel:
```bash
# Terminal 1
claude cowork "TASK 1: GST API Integration"

# Terminal 2
claude cowork "TASK 2: Monthly Turnover Calculation"

# Terminal 3
claude cowork "TASK 3: Business Vintage Auto-calc"

# Terminal 4
claude cowork "TASK 7: Lender Copilot Fix"
```

### **Week 2: UX + Communication**
Run **Batch 2** + **Task 8**:
```bash
# Terminal 1
claude cowork "TASK 4: Smart Form Pre-fill UI"

# Terminal 2
claude cowork "TASK 5: Enhanced Profile Display"

# Terminal 3
claude cowork "TASK 6: Eligibility Explanation UI"

# Terminal 4
claude cowork "TASK 8: WhatsApp Case Chat"
```

### **Week 3: Reports + Advanced**
Run **Batch 4** + **Batch 5**:
```bash
# Terminal 1
claude cowork "TASK 9: LLM Report Generation"

# Terminal 2
claude cowork "TASK 10: WhatsApp Share"

# Terminal 3 (if time)
claude cowork "TASK 11: Flexible Upload Flow"

# Terminal 4 (if time)
claude cowork "TASK 12: Bank Statement ZIP"
```

---

## ✅ Success Criteria

- [ ] GST auto-fills form (80%+ cases)
- [ ] Monthly turnover calculated from bank statements
- [ ] Copilot shows ALL matching lenders
- [ ] WhatsApp integration works per case
- [ ] Reports use narrative format
- [ ] Profile tab shows all new fields
- [ ] Eligibility explains rejections
- [ ] Direct WhatsApp sharing works

---

## 📝 Notes for Cowork Execution

**For each task:**
1. Copy the full task description
2. Paste into new Claude Cowork session
3. Cowork will have complete context
4. Let it implement independently
5. Test when done
6. Integrate into main codebase

**All tasks are independent** - no dependencies between them!
