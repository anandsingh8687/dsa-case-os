# Phase 3 - Requirements & Implementation Plan

## 📋 Overview

This document outlines the remaining features and fixes needed to complete the DSA Case OS platform.

---

## 🎯 Requirements Breakdown

### 1. Static HTML Workflow Restructuring

**Current Flow:**
```
Borrower Info → Upload Documents → Profile → Eligibility → Report
```

**New Flow:**
```
Upload Documents First → Auto-fill Borrower Info → User fills missing fields → Profile → Eligibility → Report
```

**Details:**
- Start with document upload
- Extract GST, PAN, Bank Statement data
- Auto-populate borrower details from extracted data:
  - Borrower Name (from GST tradename)
  - Entity Type (from GST constitution)
  - Pincode (from GST address)
  - Business Vintage (from GST registration date)
  - CIBIL (if found in CIBIL report)
  - Annual Turnover (from ITR/Financial statements)
- User manually fills:
  - Loan Program (Banking/Income/Hybrid)
  - Loan Amount Requested
  - Any missing fields

**Files to Modify:**
- `backend/app/static/index.html` - Reorder tabs, add upload-first UI
- `backend/app/api/v1/endpoints/cases.py` - Support partial case creation

---

### 2. Profile Tab Enhancements

**Add Missing Fields:**
- Annual Turnover (₹ Lakhs) - **CURRENTLY MISSING**
- GST Status (Active/Inactive)
- GST Registration Date
- State (from GST address)

**Current Display Issues:**
- Monthly Turnover shows (already implemented)
- Annual Turnover **MISSING** ← Need to add

**Files to Modify:**
- `backend/app/static/index.html` - Add annual turnover display
- `backend/app/services/stages/stage2_features.py` - Calculate annual turnover from ITR/financials

---

### 3. Borrower Feature Vector - Complete Display

**Current Issues:**
- GST info extracted but not fully displayed
- Business metrics incomplete

**Required Display:**

**Identity Section:**
- Full Name ✓
- PAN Number ✓
- Date of Birth ✓
- **GSTIN** ← Add
- **GST Status** ← Add

**Business Section:**
- Entity Type ✓
- Business Vintage ✓
- **GST Registration Date** ← Add
- **State** ← Add
- Pincode ✓
- Industry Type ✓

**Financial Section:**
- **Annual Turnover (from ITR)** ← Add (MISSING!)
- Monthly Turnover ✓
- Avg Monthly Balance ✓
- Monthly Credits ✓
- Bounces (12m) ✓

**Credit Section:**
- CIBIL Score ✓
- Active Loans ✓
- Overdues ✓

**Files to Modify:**
- `backend/app/static/index.html` - Add GST fields to Profile display
- `backend/app/schemas/shared.py` - Ensure all fields in BorrowerFeatureVector

---

### 4. Hard Filter Criteria - Proper Implementation

**Current Issue:**
- Only showing Tata Capital in hard filters
- Need to implement comprehensive hard filters

**Hard Filter Criteria (Must All Pass):**

1. **Applicant Age:**
   - Minimum: 21 years
   - Maximum: 65 years
   - Source: Calculate from DOB

2. **Business Vintage:**
   - Minimum: Varies by lender (0.5 - 3 years)
   - Source: GST registration date or manual input

3. **CIBIL Score:**
   - Minimum: Varies by lender (600 - 750)
   - Source: CIBIL report or manual input

4. **Active Status:**
   - GST Status: ACTIVE
   - Business Status: ACTIVE
   - All cases should match (no "inactive" lenders)

5. **Annual Turnover:**
   - Minimum: Varies by lender (₹5L - ₹50L)
   - Source: ITR/Financial statements or manual input

6. **Loan Amount:**
   - Within lender's min/max ticket size
   - Source: User input

**Implementation:**
- `backend/app/services/stages/stage4_eligibility.py` - Implement all hard filters
- `backend/app/db/schema.sql` - Ensure lender_products has all filter fields

**Example Hard Filter Logic:**
```python
def check_hard_filters(borrower, lender_product):
    failures = []

    # 1. Age check
    if borrower.age < lender_product.min_age:
        failures.append(f"Age too low ({borrower.age} < {lender_product.min_age})")

    # 2. Vintage check
    if borrower.business_vintage_years < lender_product.min_vintage_years:
        failures.append(f"Business vintage too low ({borrower.business_vintage_years} < {lender_product.min_vintage_years})")

    # 3. CIBIL check
    if borrower.cibil_score < lender_product.min_cibil:
        failures.append(f"CIBIL too low ({borrower.cibil_score} < {lender_product.min_cibil})")

    # 4. Turnover check
    if borrower.annual_turnover < lender_product.min_annual_turnover:
        failures.append(f"Annual turnover too low (₹{borrower.annual_turnover}L < ₹{lender_product.min_annual_turnover}L)")

    # 5. Active status check
    if borrower.gst_status != "Active":
        failures.append("GST status is not Active")

    return failures
```

---

### 5. Dynamic Eligibility Recommendations

**Current Issue:**
- Recommendations are static/hardcoded
- Need dynamic recommendations based on actual rejection reasons

**Implementation:**
- Analyze ALL rejected lenders
- Identify most common rejection reasons
- Prioritize improvements by impact

**Example Logic:**
```python
def generate_dynamic_recommendations(borrower, failed_lenders):
    rejection_counts = {
        "cibil_low": 0,
        "vintage_low": 0,
        "turnover_low": 0,
        "age_issue": 0
    }

    # Count rejection reasons
    for lender in failed_lenders:
        for reason in lender.failure_reasons:
            if "CIBIL" in reason:
                rejection_counts["cibil_low"] += 1
            elif "vintage" in reason:
                rejection_counts["vintage_low"] += 1
            elif "turnover" in reason:
                rejection_counts["turnover_low"] += 1

    # Generate recommendations sorted by impact
    recommendations = []

    # Most impactful first
    if rejection_counts["cibil_low"] > rejection_counts["vintage_low"]:
        recommendations.append({
            "priority": 1,
            "issue": "CIBIL Score",
            "current": borrower.cibil_score,
            "target": "700+",
            "impact": f"Would unlock {rejection_counts['cibil_low']} more lenders",
            "action": "Pay off existing dues, reduce credit utilization"
        })

    return recommendations
```

**Files to Modify:**
- `backend/app/static/index.html` - Dynamic recommendation display
- `backend/app/services/stages/stage4_eligibility.py` - Generate dynamic recs

---

### 6. FOIR Calculation Documentation

**FOIR = Fixed Obligation to Income Ratio**

**Formula:**
```
FOIR = (Total Monthly EMI Obligations / Gross Monthly Income) × 100
```

**Components:**
- **Monthly EMI Obligations:**
  - Existing loan EMIs
  - Credit card minimum payments
  - Other recurring debts

- **Gross Monthly Income:**
  - From ITR: Annual Income / 12
  - From Bank Statements: Average monthly credits
  - From Salary Slips (if available)

**Acceptance Criteria:**
- Most lenders: FOIR < 50%
- Conservative lenders: FOIR < 40%
- Aggressive lenders: FOIR < 60%

**Current Implementation:**
- Need to verify if this is calculated in `stage2_features.py`
- If missing, need to implement

**Files to Check:**
- `backend/app/services/stages/stage2_features.py`
- `backend/app/services/stages/stage2_bank_analyzer.py`

---

### 7. WhatsApp Integration - Advanced Features

#### 7A. WhatsApp Initiation in Checklist

**Scenario:**
- User uploads documents
- Some required documents are missing
- Show "Send WhatsApp Request" button

**UI Changes:**
```html
<div class="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
  <h4 class="font-semibold text-yellow-800 mb-2">⚠️ Missing Documents</h4>
  <ul class="text-sm text-yellow-700 mb-3">
    <li>• Bank Statements (6 months)</li>
    <li>• ITR (Last 2 years)</li>
  </ul>
  <button @click="initiateWhatsApp()" class="btn-primary">
    📱 Request via WhatsApp
  </button>
</div>
```

**Flow:**
1. User clicks "Request via WhatsApp"
2. QR code appears for WhatsApp Web linking
3. User scans QR with their WhatsApp account
4. System sends template message to customer:
   ```
   Hi {customer_name},

   We need the following documents for your loan application (Case: {case_id}):
   • Bank Statements (last 6 months)
   • ITR (last 2 years)

   Please share these documents via WhatsApp.

   Thanks,
   {dsa_name}
   ```

**Files to Modify:**
- `backend/app/static/index.html` - Add WhatsApp initiation UI in Checklist tab
- `backend/app/api/v1/endpoints/whatsapp.py` - Add document request endpoint

#### 7B. Send to Customer (Replace Copy Text)

**Current Implementation:**
- Report tab has "Copy Text" button
- User manually copies and pastes to WhatsApp

**New Implementation:**
- Replace with "Send to Customer" button
- Automatically sends via WhatsApp Web

**UI Changes:**
```html
<!-- OLD -->
<button @click="navigator.clipboard.writeText(report.whatsapp_summary)">
  Copy Text
</button>

<!-- NEW -->
<button @click="sendWhatsAppToCustomer()" class="btn-primary">
  📱 Send to Customer
</button>
```

**Flow:**
1. User generates report
2. Clicks "Send to Customer"
3. If WhatsApp not linked:
   - Show QR code modal
   - User scans and links
4. If WhatsApp linked:
   - Show customer number input (or use saved number)
   - Sends WhatsApp message with report summary
   - Shows success toast: "Report sent to customer via WhatsApp!"

**Files to Modify:**
- `backend/app/static/index.html` - Replace Copy Text with Send button
- `backend/app/api/v1/endpoints/whatsapp.py` - Add send_report_to_customer endpoint

---

## 🗂️ Implementation Priority

### Phase 3A (High Priority - Core Fixes)
1. ✅ Fix hard filter criteria (eligibility working properly)
2. ✅ Add annual turnover to profile/features
3. ✅ Dynamic eligibility recommendations
4. ✅ Static HTML workflow restructuring

### Phase 3B (Medium Priority - WhatsApp)
5. ✅ WhatsApp initiation in Checklist
6. ✅ Send to Customer button (replace Copy Text)
7. ✅ WhatsApp QR linking flow

### Phase 3C (Low Priority - Polish)
8. ✅ Complete GST info display in Profile
9. ✅ FOIR calculation verification
10. ✅ End-to-end testing

---

## 📊 Success Metrics

**Phase 3 Complete When:**
- [ ] Static HTML starts with upload-first workflow
- [ ] Annual turnover displays in Profile
- [ ] All hard filters implemented (age, vintage, CIBIL, status, turnover)
- [ ] Dynamic recommendations based on rejections
- [ ] WhatsApp initiation works for missing docs
- [ ] "Send to Customer" replaces "Copy Text"
- [ ] Complete end-to-end case creation works
- [ ] All features tested and documented

---

## 📁 Files to Modify Summary

| File | Changes Needed |
|------|----------------|
| `backend/app/static/index.html` | Workflow reorder, annual turnover, WhatsApp UI |
| `backend/app/services/stages/stage4_eligibility.py` | Hard filters, dynamic recs |
| `backend/app/services/stages/stage2_features.py` | Annual turnover extraction |
| `backend/app/api/v1/endpoints/whatsapp.py` | Document request, send to customer |
| `backend/app/api/v1/endpoints/cases.py` | Support upload-first flow |
| `backend/app/db/schema.sql` | Verify lender hard filter fields |

---

## 🚀 Next Steps

1. Review this plan
2. Confirm priorities
3. Start implementation with Phase 3A
4. Test each feature incrementally
5. Move to Phase 3B and 3C

---

**Document Version:** 1.0
**Date:** February 11, 2026
**Status:** Planning Complete, Ready for Implementation
