"""Shared enums used across all modules - THE source of truth for all status/type values."""
from enum import Enum


# ─── Case Lifecycle ────────────────────────────────────────────
class CaseStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    DOCUMENTS_CLASSIFIED = "documents_classified"
    FEATURES_EXTRACTED = "features_extracted"
    ELIGIBILITY_SCORED = "eligibility_scored"
    REPORT_GENERATED = "report_generated"
    SUBMITTED = "submitted"
    FAILED = "failed"


# ─── Document Types ────────────────────────────────────────────
class DocumentType(str, Enum):
    AADHAAR = "aadhaar"
    PAN_PERSONAL = "pan_personal"
    PAN_BUSINESS = "pan_business"
    GST_CERTIFICATE = "gst_certificate"
    GST_RETURNS = "gst_returns"
    BANK_STATEMENT = "bank_statement"
    ITR = "itr"
    FINANCIAL_STATEMENTS = "financial_statements"
    CIBIL_REPORT = "cibil_report"
    UDYAM_SHOP_LICENSE = "udyam_shop_license"
    PROPERTY_DOCUMENTS = "property_documents"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    OCR_COMPLETE = "ocr_complete"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    FAILED = "failed"


# ─── Loan Program ──────────────────────────────────────────────
class ProgramType(str, Enum):
    BANKING = "banking"
    INCOME = "income"
    HYBRID = "hybrid"


# ─── Business Entity ───────────────────────────────────────────
class EntityType(str, Enum):
    PROPRIETORSHIP = "proprietorship"
    PARTNERSHIP = "partnership"
    LLP = "llp"
    PVT_LTD = "pvt_ltd"
    PUBLIC_LTD = "public_ltd"
    TRUST = "trust"
    SOCIETY = "society"
    HUF = "huf"


# ─── Eligibility ───────────────────────────────────────────────
class HardFilterStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ApprovalProbability(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─── Confidence Levels ─────────────────────────────────────────
class ConfidenceLevel(str, Enum):
    HIGH = "high"       # > 0.85
    MEDIUM = "medium"   # 0.65 - 0.85
    LOW = "low"         # < 0.65
