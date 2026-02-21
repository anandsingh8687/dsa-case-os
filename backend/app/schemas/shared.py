"""Shared Pydantic schemas - used as interface contracts between all modules.
Every Cowork task MUST import and use these schemas for inter-module communication."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date
from uuid import UUID

from app.core.enums import (
    CaseStatus, DocumentType, DocumentStatus, ProgramType,
    EntityType, HardFilterStatus, ApprovalProbability
)


# ═══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════

# ─── User ──────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: str
    phone: Optional[str] = None
    full_name: str
    password: str
    organization: Optional[str] = None

class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── Case ──────────────────────────────────────────────────────
class CaseCreate(BaseModel):
    borrower_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    program_type: Optional[ProgramType] = None
    industry_type: Optional[str] = None
    pincode: Optional[str] = None
    loan_amount_requested: Optional[float] = None

class CaseUpdate(BaseModel):
    borrower_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    program_type: Optional[ProgramType] = None
    business_vintage_years: Optional[float] = None
    cibil_score_manual: Optional[int] = None
    monthly_turnover_manual: Optional[float] = None
    industry_type: Optional[str] = None
    pincode: Optional[str] = None
    loan_amount_requested: Optional[float] = None

class CaseResponse(BaseModel):
    id: UUID
    case_id: str
    status: CaseStatus
    program_type: Optional[ProgramType]
    borrower_name: Optional[str]
    entity_type: Optional[str]
    completeness_score: float
    # Manual override fields
    cibil_score_manual: Optional[int] = None
    business_vintage_years: Optional[float] = None
    monthly_turnover_manual: Optional[float] = None
    industry_type: Optional[str] = None
    pincode: Optional[str] = None
    loan_amount_requested: Optional[float] = None
    gstin: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CaseSummary(BaseModel):
    """Lightweight case listing for dashboard."""
    case_id: str
    borrower_name: Optional[str]
    status: CaseStatus
    completeness_score: float
    created_at: datetime


# ─── Document ──────────────────────────────────────────────────
class DocumentResponse(BaseModel):
    id: UUID
    original_filename: Optional[str]
    doc_type: Optional[DocumentType] = None
    classification_confidence: Optional[float] = 0.0
    status: DocumentStatus
    page_count: Optional[int] = None
    created_at: datetime

class DocumentChecklist(BaseModel):
    """Output of Stage 1 checklist engine."""
    program_type: ProgramType
    available: List[DocumentType]
    missing: List[DocumentType]
    unreadable: List[str]           # filenames that failed OCR
    optional_present: List[DocumentType]
    completeness_score: float       # 0-100


class ManualFieldPrompt(BaseModel):
    """Prompt for progressive data capture when documents are missing."""
    field_name: str                 # e.g., "cibil_score_manual"
    label: str                      # e.g., "CIBIL Score"
    reason: str                     # e.g., "CIBIL report not uploaded"
    field_type: str                 # "number" | "text" | "select"
    current_value: Optional[Any] = None


# ─── Extracted Fields ──────────────────────────────────────────
class ExtractedFieldItem(BaseModel):
    field_name: str
    field_value: Optional[str]
    confidence: float
    source: str = "extraction"


# ─── Borrower Feature Vector ──────────────────────────────────
class BorrowerFeatureVector(BaseModel):
    """THE canonical borrower profile - output of Stage 2, input to Stage 4."""
    # Identity
    full_name: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    dob: Optional[date] = None

    # Business
    entity_type: Optional[EntityType] = None
    business_vintage_years: Optional[float] = None
    gstin: Optional[str] = None
    industry_type: Optional[str] = None
    pincode: Optional[str] = None

    # Financial
    annual_turnover: Optional[float] = None           # in Lakhs
    avg_monthly_balance: Optional[float] = None
    monthly_credit_avg: Optional[float] = None
    monthly_turnover: Optional[float] = None          # Average monthly credits (same as monthly_credit_avg)
    emi_outflow_monthly: Optional[float] = None
    bounce_count_12m: Optional[int] = None
    cash_deposit_ratio: Optional[float] = None
    itr_total_income: Optional[float] = None          # in Lakhs

    # Credit
    cibil_score: Optional[int] = None
    active_loan_count: Optional[int] = None
    overdue_count: Optional[int] = None
    enquiry_count_6m: Optional[int] = None

    # Meta
    feature_completeness: float = 0.0


# ─── Lender ────────────────────────────────────────────────────
class LenderProductRule(BaseModel):
    """One lender-product combination from the knowledge base.
    Maps directly to 'Lender Policy.xlsx - BL Lender Policy.csv' columns."""
    lender_name: str
    product_name: str                                 # BL, STBL, HTBL, MTBL, SBL, PL, OD, LAP, Digital, Direct
    program_type: Optional[ProgramType] = None

    # Hard filters (from CSV)
    min_vintage_years: Optional[float] = None         # "Min. Vintage"
    min_cibil_score: Optional[int] = None             # "Min. Score"
    min_turnover_annual: Optional[float] = None       # "Min. Turnover" in Lakhs
    max_ticket_size: Optional[float] = None           # "Max Ticket size" in Lakhs
    min_abb: Optional[float] = None                   # "ABB" minimum avg bank balance
    abb_to_emi_ratio: Optional[str] = None            # ABB-to-EMI ratio rule
    eligible_entity_types: List[str] = []             # "Entity" parsed
    age_min: Optional[int] = None                     # "Age" range min
    age_max: Optional[int] = None                     # "Age" range max

    # DPD / Bureau rules
    no_30plus_dpd_months: Optional[int] = None        # lookback months for no 30+ DPD
    no_60plus_dpd_months: Optional[int] = None
    no_90plus_dpd_months: Optional[int] = None
    max_enquiries_rule: Optional[str] = None
    max_overdue_amount: Optional[float] = None
    emi_bounce_rule: Optional[str] = None
    bureau_check_detail: Optional[str] = None

    # Banking & Docs
    banking_months_required: Optional[int] = None
    bank_source_type: Optional[str] = None            # AA, PDF, Scorme
    gst_required: bool = False
    ownership_proof_required: bool = False
    kyc_documents: Optional[str] = None
    tenor_min_months: Optional[int] = None
    tenor_max_months: Optional[int] = None
    interest_rate_range: Optional[str] = None
    processing_fee_pct: Optional[float] = None
    expected_tat_days: Optional[int] = None

    # Verification
    tele_pd_required: bool = False
    video_kyc_required: bool = False
    fi_required: bool = False

    # Status
    policy_available: bool = True
    serviceable_pincodes_count: int = 0               # number of pincodes served

    # Legacy
    max_foir: Optional[float] = None
    excluded_industries: List[str] = []
    min_ticket_size: Optional[float] = None
    required_documents: List[str] = []


class BankAnalysisResult(BaseModel):
    """Output from Credilo bank statement parser + metrics computation.
    The credilo parser extracts transactions; this adds computed metrics."""
    # From credilo parser
    bank_detected: Optional[str] = None
    account_number: Optional[str] = None
    transaction_count: int = 0
    statement_period_months: int = 0

    # Computed financial metrics (added on top of credilo)
    avg_monthly_balance: Optional[float] = None
    monthly_credit_avg: Optional[float] = None
    monthly_debit_avg: Optional[float] = None
    emi_outflow_monthly: Optional[float] = None
    bounce_count_12m: int = 0
    cash_deposit_ratio: Optional[float] = None
    peak_balance: Optional[float] = None
    min_balance: Optional[float] = None
    total_credits_12m: Optional[float] = None
    total_debits_12m: Optional[float] = None

    # Per-month breakdown
    monthly_summary: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    source: Optional[str] = None
    credilo_summary: Dict[str, Any] = Field(default_factory=dict)


# ─── Eligibility ───────────────────────────────────────────────
class EligibilityResult(BaseModel):
    """Output per lender from Stage 4."""
    lender_name: str
    product_name: str
    hard_filter_status: HardFilterStatus
    hard_filter_details: Dict[str, Any] = {}
    eligibility_score: Optional[float] = None        # 0-100
    approval_probability: Optional[ApprovalProbability] = None
    expected_ticket_min: Optional[float] = None
    expected_ticket_max: Optional[float] = None
    confidence: float = 0.0
    missing_for_improvement: List[str] = []
    rank: Optional[int] = None

class EligibilityResponse(BaseModel):
    """Full eligibility output for a case."""
    case_id: str
    total_lenders_evaluated: int
    lenders_passed: int
    results: List[EligibilityResult]
    rejection_reasons: List[str] = []        # Why lenders rejected (when lenders_passed = 0)
    suggested_actions: List[str] = []        # What borrower can improve
    dynamic_recommendations: List[Dict[str, Any]] = []  # Prioritized recommendations with impact analysis


# ─── Case Report ───────────────────────────────────────────────
class CaseReportData(BaseModel):
    """Structured data for Stage 5 report generation."""
    case_id: str
    borrower_profile: BorrowerFeatureVector
    checklist: DocumentChecklist
    strengths: List[str]
    risk_flags: List[str]
    lender_matches: List[EligibilityResult]
    submission_strategy: str
    missing_data_advisory: List[str]
    expected_loan_range: Optional[str] = None


# ─── Copilot ───────────────────────────────────────────────────
class CopilotHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotQuery(BaseModel):
    query: str
    history: List[CopilotHistoryMessage] = []

class CopilotResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    response_time_ms: int


# ─── OCR ───────────────────────────────────────────────────────
class OCRResult(BaseModel):
    """Output from Stage 1 OCR service."""
    text: str
    confidence: float                   # 0-1 average confidence score
    page_count: int
    method: str                          # "pymupdf" or "tesseract"
