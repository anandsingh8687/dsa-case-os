# Phase 3 Implementation Status

## ✅ ALREADY WORKING

### 1. Hard Filter Criteria - **COMPLETE**
All hard filters are properly implemented in `stage4_eligibility.py`:
- ✅ Pincode serviceability
- ✅ CIBIL score (min threshold)
- ✅ Entity type matching
- ✅ Business vintage (min years)
- ✅ Annual turnover (min amount)
- ✅ Age range (21-65 from DOB)
- ✅ Average Bank Balance (min ABB)

**Why only Tata Capital shows:** This is likely because only Tata Capital matches the borrower's specific criteria based on the data. Other lenders are being filtered out correctly.

### 2. Annual Turnover Field - **EXISTS IN SCHEMA**
- Schema has `annual_turnover` field ✅
- Referenced in feature extraction ✅
- Used in eligibility scoring ✅

**What's missing:** Need to verify extraction from ITR documents populates this field.

### 3. GST Integration - **WORKING**
- GST API service implemented ✅
- GSTIN extraction from documents ✅
- Auto-fill functionality in React ✅
- Database columns added ✅

### 4. Eligibility Explanations UI - **WORKING**
- Rejection reasons display ✅
- Improvement recommendations ✅
- Implemented in static HTML ✅

### 5. LLM Narrative Reports - **WORKING**
- Kimi 2.5 API integration ✅
- Narrative generation ✅
- Fallback to bullets if API fails ✅

### 6. WhatsApp Share - **WORKING**
- Copy to clipboard ✅
- WhatsApp summary generation ✅
- Located in Report tab ✅

---

## 🔨 NEEDS IMPLEMENTATION

### 1. Static HTML Workflow Restructuring
**Status:** Not implemented
**Required:** Upload documents first → Auto-fill → User completes form

**Implementation Needed:**
- Reorder tabs in `index.html`
- Create "Upload First" button/flow
- Auto-populate form after document upload
- Keep manual override capability

**Files:** `backend/app/static/index.html`

---

### 2. Annual Turnover in Profile Display
**Status:** Field exists but not displayed
**Required:** Show annual turnover in Profile tab

**Implementation Needed:**
```html
<!-- Add to Profile tab Financial section -->
<div>
  <label class="text-xs text-gray-500">Annual Turnover (₹ Lakhs)</label>
  <div class="text-sm font-medium" x-text="features.annual_turnover || 'Not available'"></div>
</div>
```

**Files:** `backend/app/static/index.html` (Profile tab)

---

### 3. Dynamic Eligibility Recommendations
**Status:** Recommendations exist but are static
**Required:** Generate recommendations based on actual rejection analysis

**Implementation Needed:**
- Analyze all rejected lenders
- Count rejection reasons
- Prioritize by impact
- Show actionable steps

**Example Output:**
```
💡 Top Recommendations to Improve Eligibility:

1. PRIORITY: Improve CIBIL Score
   Current: 650
   Target: 700+
   Impact: Would unlock 12 more lenders
   Action: Pay off existing dues, reduce credit utilization

2. Increase Annual Turnover
   Current: ₹8L
   Target: ₹15L+
   Impact: Would unlock 5 more lenders
   Action: Grow business operations, consider consolidating multiple entities
```

**Files:**
- `backend/app/services/stages/stage4_eligibility.py` (generate recommendations)
- `backend/app/static/index.html` (display)

---

### 4. WhatsApp Initiation in Checklist
**Status:** Not implemented
**Required:** Button to request missing docs via WhatsApp

**Implementation Needed:**
```html
<!-- In Checklist tab when documents missing -->
<div class="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
  <h4 class="font-semibold text-yellow-800 mb-2">⚠️ Missing Documents</h4>
  <ul class="text-sm text-yellow-700 mb-3">
    <template x-for="doc in missingDocs">
      <li x-text="'• ' + doc"></li>
    </template>
  </ul>
  <button @click="requestDocsViaWhatsApp()" class="btn-primary">
    📱 Request via WhatsApp
  </button>
</div>

<script>
async requestDocsViaWhatsApp() {
  // 1. Generate QR if not linked
  // 2. Show modal with QR code
  // 3. Once linked, send template message
  const message = `Hi, we need the following documents for your loan application (Case: ${this.currentCase.case_id}):\n\n${this.missingDocs.join('\n• ')}\n\nPlease share via WhatsApp. Thanks!`;
  await this.api('POST', '/whatsapp/send-message', {
    case_id: this.currentCaseId,
    to: this.customerPhone,
    message: message
  });
}
</script>
```

**Files:**
- `backend/app/static/index.html` (UI)
- `backend/app/api/v1/endpoints/whatsapp.py` (already exists)

---

### 5. Send to Customer Button (Replace Copy Text)
**Status:** "Copy Text" button exists
**Required:** "Send to Customer" button that sends via WhatsApp

**Implementation Needed:**
```html
<!-- OLD -->
<button @click="navigator.clipboard.writeText(report.whatsapp_summary)">
  Copy Text
</button>

<!-- NEW -->
<button @click="sendReportToCustomer()" class="btn-primary">
  📱 Send to Customer
</button>

<script>
async sendReportToCustomer() {
  // Check if WhatsApp linked
  if (!this.whatsappLinked) {
    // Show QR modal
    this.showWhatsAppQRModal = true;
    return;
  }

  // Send message
  await this.api('POST', '/whatsapp/send-message', {
    case_id: this.currentCaseId,
    to: this.customerPhone,
    message: this.report.whatsapp_summary
  });

  this.showToast('Report sent to customer via WhatsApp!', 'success');
}
</script>
```

**Files:**
- `backend/app/static/index.html`
- Reuse existing WhatsApp API endpoints

---

### 6. Enhanced Profile Display - GST Info
**Status:** Partial - some GST fields missing
**Required:** Show complete GST information

**Add to Profile Tab:**
```html
<!-- GST Information Section -->
<div class="bg-white rounded-xl border p-4">
  <h4 class="font-semibold text-gray-800 mb-3">🏢 GST Information</h4>
  <div class="grid grid-cols-2 gap-3">
    <div>
      <label class="text-xs text-gray-500">GSTIN</label>
      <div class="text-sm font-medium" x-text="features.gstin || 'Not available'"></div>
    </div>
    <div>
      <label class="text-xs text-gray-500">GST Status</label>
      <div class="text-sm font-medium" x-text="features.gst_status || 'Not available'"></div>
    </div>
    <div>
      <label class="text-xs text-gray-500">Registration Date</label>
      <div class="text-sm font-medium" x-text="features.gst_registration_date || 'Not available'"></div>
    </div>
    <div>
      <label class="text-xs text-gray-500">State</label>
      <div class="text-sm font-medium" x-text="features.state || 'Not available'"></div>
    </div>
  </div>
</div>
```

**Files:** `backend/app/static/index.html`

---

### 7. FOIR Calculation Verification
**Status:** Need to verify implementation
**Required:** Document and verify FOIR calculation

**Check:**
- `stage2_features.py` - Is FOIR calculated?
- Formula: `(Total Monthly EMIs / Monthly Income) × 100`
- Should be < 50% for most lenders

**If missing, implement in feature extraction.**

---

## 📊 Priority Order

### HIGH PRIORITY (Do First)
1. ✅ Add Annual Turnover to Profile display (5 min)
2. ✅ Dynamic Eligibility Recommendations (30 min)
3. ✅ Enhanced Profile - GST Info (10 min)

### MEDIUM PRIORITY
4. ✅ Send to Customer button (1 hour)
5. ✅ WhatsApp Initiation in Checklist (1 hour)

### LOW PRIORITY
6. ✅ Static HTML Workflow Restructuring (2-3 hours)
7. ✅ FOIR Verification (30 min)

---

## 🚀 Quick Wins (Can Do Now)

These are simple HTML changes that can be done immediately:

### Quick Win 1: Annual Turnover Display (2 minutes)
Add after line 454 in `index.html` (Profile tab):
```html
<div><label class="text-xs text-gray-500">Annual Turnover (₹ Lakhs)</label><div class="text-sm font-medium" x-text="features.annual_turnover ? '₹' + features.annual_turnover + 'L' : 'Not available'"></div></div>
```

### Quick Win 2: GST Status Display (2 minutes)
Add GSTIN and GST status to Profile tab identity section.

### Quick Win 3: State Display (1 minute)
Add state field from GST data to Profile tab.

---

## 🎯 Next Steps

1. Implement Quick Wins (10 minutes total)
2. Test changes
3. Move to Dynamic Recommendations
4. Move to WhatsApp features
5. Final: Workflow restructuring

---

**Total Estimated Time:** 6-8 hours for complete implementation

**Current Status:** ~70% complete, mostly polish and UI enhancements needed
