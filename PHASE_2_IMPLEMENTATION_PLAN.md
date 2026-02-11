# Phase 2 - Smart Intelligence & UX Enhancements

## 🎯 Overview
Make DSA Case OS more intelligent and user-friendly by automating data extraction, improving AI responses, and streamlining workflows.

---

## 📋 Feature Breakdown

### **1. Smart Document-Based Form Pre-filling** ⭐ HIGH PRIORITY

**Problem:** Users have to manually fill company name, entity type, industry, pincode - but this data is already in their documents!

**Solution:**
1. Allow users to upload documents FIRST (before filling form)
2. Auto-extract GST number from GST returns/certificates
3. Call GST API to fetch:
   - Company legal name
   - Entity type (Proprietorship, Partnership, LLP, Pvt Ltd, etc.)
   - Industry/Business activity
   - Address → Extract pincode
4. Pre-populate the form with this data
5. User only fills: Loan program, Loan amount

**Technical Approach:**
```python
# Stage 0: After document upload
1. Run OCR on all documents
2. Classify documents (find GST returns)
3. Extract GSTIN using regex pattern: \d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}
4. Call GST API: POST /api/gst/{gstin}/details
5. Parse response and save to case metadata
6. Frontend: Check if GST data exists, pre-fill form
```

**API Integration:**
```python
# backend/app/services/gst_api.py
class GSTAPIService:
    def fetch_company_details(self, gstin: str) -> dict:
        # Call external GST API
        # Return: company_name, entity_type, industry, address, pincode
```

**Files to modify:**
- `backend/app/services/gst_api.py` (NEW)
- `backend/app/services/stages/stage0_case_entry.py` (add GST extraction)
- `backend/app/api/v1/endpoints/cases.py` (add GST data endpoint)
- `frontend/src/pages/NewCase.jsx` (check for GST data, pre-fill)

---

### **2. Flexible Upload Flow** ⭐ HIGH PRIORITY

**Problem:** Current flow forces: Form → Upload → Process. But users might have documents ready first!

**Solution:**
Two possible entry points:
- **Option A:** Fill form first (current flow)
- **Option B:** Upload documents first → Auto-extract → Confirm details → Process

**UI Flow:**
```
Landing → Dashboard → "New Case" button

New Case Screen:
┌─────────────────────────────────┐
│  Create New Case                │
│                                 │
│  [ ] Start with documents       │  ← New option
│      (We'll extract details)    │
│                                 │
│  [ ] Fill details manually      │  ← Current flow
│      (Provide info first)       │
└─────────────────────────────────┘
```

**Technical Approach:**
```javascript
// frontend/src/pages/NewCase.jsx
const [mode, setMode] = useState('documents'); // or 'manual'

if (mode === 'documents') {
  // Show upload dropzone first
  // After upload → extract GST → show pre-filled form for confirmation
}

if (mode === 'manual') {
  // Current flow: form → upload → process
}
```

---

### **3. LLM-Based Report Generation** ⭐ MEDIUM PRIORITY

**Problem:** Submission strategy shows bullet points - not professional, hard to read.

**Current Output:**
```
**Primary Target:** Tata Capital - Digital
- Eligibility Score: 85/100
- Approval Probability: HIGH
```

**Desired Output:**
```
Based on the borrower's profile analysis, we recommend approaching Tata Capital's
Digital Business Loan product as the primary target. This lender shows strong
alignment with an eligibility score of 85/100 and high approval probability.
The borrower meets all hard filters including minimum vintage requirements (5 years),
CIBIL threshold (740), and average bank balance criteria. Expected ticket size
ranges from ₹2.5L to ₹10L with competitive interest rates.

For optimal submission strategy, we suggest preparing all required documents including
GST returns, bank statements, and KYC before approaching the lender...
```

**Technical Approach:**
```python
# backend/app/services/stages/stage5_report.py

async def generate_submission_strategy_llm(eligibility_results, feature_vector):
    prompt = f"""
    Generate a professional submission strategy paragraph for a business loan application.

    Borrower Profile:
    - CIBIL: {feature_vector.cibil_score}
    - Business Vintage: {feature_vector.business_vintage_years} years
    - Average Balance: ₹{feature_vector.avg_monthly_balance}

    Top Lender Match:
    - Lender: {top_lender.lender_name}
    - Product: {top_lender.product_name}
    - Score: {top_lender.eligibility_score}/100
    - Probability: {top_lender.approval_probability}

    Write a 2-3 paragraph professional strategy in narrative format.
    """

    # Call Claude API (using existing copilot engine)
    return await copilot_service.generate(prompt)
```

---

### **4. WhatsApp Direct Share** ⭐ MEDIUM PRIORITY

**Problem:** "Copy Text" button is clunky - users have to manually paste into WhatsApp.

**Solution:** Direct WhatsApp share with QR code or number input.

**Implementation Options:**

**Option A: WhatsApp API (Requires Business Account)**
```python
# backend/app/services/whatsapp_api.py
def send_whatsapp_message(phone_number: str, message: str):
    # Use WhatsApp Business API
    # Send message directly
```

**Option B: WhatsApp Web Link (Simpler, no API needed)**
```javascript
// frontend - Generate WhatsApp link
const shareToWhatsApp = (phoneNumber, message) => {
  const encoded = encodeURIComponent(message);
  const url = `https://wa.me/${phoneNumber}?text=${encoded}`;
  window.open(url, '_blank');
};
```

**UI:**
```html
<!-- Replace Copy Text with -->
<button onclick="openWhatsAppModal()">
  📱 Share via WhatsApp
</button>

<!-- Modal shows -->
<dialog>
  <input placeholder="Enter WhatsApp number (with country code)" />
  <button>Send Message</button>

  <!-- OR -->

  <img src="/qr-code-for-whatsapp" />
  <p>Scan to share on your phone</p>
</dialog>
```

---

### **5. Lender Copilot Enhancements** ⭐ HIGH PRIORITY

**Problem 1:** Incomplete responses - Shows 4 lenders when 15 exist.

**Root Cause:** LLM truncating response or retrieval limiting results.

**Fix:**
```python
# backend/app/services/stages/stage7_copilot.py

# Current (wrong):
results = await db.fetchmany(10)  # Only gets 10

# Fixed:
results = await db.fetchall()  # Get ALL matching lenders

# Then format ALL results in response:
response = f"Found {len(results)} lenders accepting CIBIL below 650:\n\n"
for lender in results:
    response += f"- {lender.lender_name} - {lender.product_name}\n"
```

**Problem 2:** No general knowledge - Can't answer "What is FOIR?" or "How to improve CIBIL?"

**Solution:** Add research engine (internet search) for general queries.

**Technical Approach:**
```python
# backend/app/services/stages/stage7_copilot.py

async def answer_query(query: str, case_id: str):
    # Step 1: Classify query type
    query_type = classify_query(query)  # "lender_policy" or "general_knowledge"

    if query_type == "lender_policy":
        # Use existing RAG pipeline (knowledge base)
        return await rag_pipeline(query, case_id)

    elif query_type == "general_knowledge":
        # Use web search + LLM
        search_results = await web_search(query)  # Tavily/Perplexity API
        context = format_search_results(search_results)

        prompt = f"""
        Based on these search results:
        {context}

        Answer this question: {query}

        Format as a helpful, concise response.
        """

        return await claude_api.generate(prompt)
```

**Web Search Integration:**
- Option A: Tavily API (fast, built for AI)
- Option B: Perplexity API (AI-native search)
- Option C: SerpAPI (Google results)

---

### **6. Fix Profile Re-run Extraction** ⭐ LOW PRIORITY

**Status:** Needs investigation. Currently working but button behavior unclear.

**Action:** Test manually and identify specific issue.

---

## 🎯 Implementation Priority

### **Phase 2A - Week 1 (High Impact, Quick Wins)**

1. ✅ **GST Number Extraction** (2-3 hours)
   - Add regex extraction from OCR text
   - Save to case metadata

2. ✅ **GST API Integration** (3-4 hours)
   - Create GST API service
   - Call on GST number detection
   - Store company details

3. ✅ **Form Pre-filling** (2-3 hours)
   - Check for GST data on New Case page
   - Pre-populate fields
   - Show "Auto-filled from GST" indicator

4. ✅ **Lender Copilot - Complete Results Fix** (1-2 hours)
   - Ensure ALL matching lenders returned
   - Format properly in response

### **Phase 2B - Week 2 (UX Improvements)**

5. ✅ **Flexible Upload Flow** (4-6 hours)
   - Add mode selector
   - Restructure New Case page
   - Handle both flows

6. ✅ **WhatsApp Share** (3-4 hours)
   - Add WhatsApp link generation
   - Create phone number input modal
   - QR code option

### **Phase 2C - Week 3 (Advanced Features)**

7. ✅ **LLM-Based Report** (4-5 hours)
   - Create narrative generator
   - Integrate with report pipeline
   - Format PDF properly

8. ✅ **Copilot Research Engine** (6-8 hours)
   - Add web search API
   - Query classification
   - Hybrid response generation

---

## 📊 Success Metrics

- **GST Auto-fill:** 80%+ of cases have auto-populated data
- **Copilot Completeness:** 100% of matching lenders shown
- **Report Quality:** Narrative format, professional tone
- **WhatsApp Share:** 50%+ users prefer direct share over copy
- **User Flow Time:** 30% reduction in case creation time

---

## 🔧 Technical Requirements

### **New Dependencies:**
```bash
# Python
pip install anthropic  # Claude API for LLM generation
pip install tavily-python  # Web search for research engine

# Optional
pip install qrcode  # QR code generation for WhatsApp
```

### **APIs Needed:**
1. GST API (user will provide)
2. Claude API (already have via Anthropic)
3. Web Search API (Tavily/Perplexity - need to choose)

### **Environment Variables:**
```bash
# .env
GST_API_KEY=your_gst_api_key
GST_API_URL=https://api.gst.gov.in/...
TAVILY_API_KEY=your_tavily_key  # For research engine
CLAUDE_API_KEY=your_claude_key  # Already have
```

---

## 🚀 Let's Start!

**Immediate Next Steps:**

1. **User:** Provide GST API details (endpoint, auth, response format)
2. **Me:** Implement GST extraction + API integration
3. **User:** Test and provide feedback
4. **Iterate:** Move to next features

**Which feature should we start with?**
- A. GST Auto-fill (smart form)
- B. Lender Copilot fixes (complete results)
- C. WhatsApp share
- D. Flexible upload flow

Let me know and I'll start implementing! 🎯
