"""SQLAlchemy models for Cases and Documents."""
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import uuid4

from app.models.base import Base


class Case(Base):
    """Case model - represents a loan application case."""
    __tablename__ = "cases"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(String(20), unique=True, nullable=False, index=True)
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="created", index=True)
    program_type = Column(String(10), nullable=True)

    # Borrower basics (manual overrides)
    borrower_name = Column(String(255), nullable=True)
    entity_type = Column(String(20), nullable=True)
    business_vintage_years = Column(Float, nullable=True)
    cibil_score_manual = Column(Integer, nullable=True)
    monthly_turnover_manual = Column(Float, nullable=True)
    industry_type = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    loan_amount_requested = Column(Float, nullable=True)

    # GST data
    gstin = Column(String(15), nullable=True, index=True)
    gst_data = Column(JSONB, nullable=True)
    gst_fetched_at = Column(DateTime(timezone=True), nullable=True)

    # WhatsApp integration
    whatsapp_number = Column(String(20), nullable=True, index=True)
    whatsapp_session_id = Column(String(100), nullable=True, index=True)
    whatsapp_linked_at = Column(DateTime(timezone=True), nullable=True)
    whatsapp_qr_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Completeness
    completeness_score = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    document_processing_jobs = relationship("DocumentProcessingJob", back_populates="case", cascade="all, delete-orphan")
    extracted_fields = relationship("ExtractedField", back_populates="case", cascade="all, delete-orphan")
    borrower_features = relationship("BorrowerFeature", back_populates="case", cascade="all, delete-orphan")


class Document(Base):
    """Document model - represents uploaded files."""
    __tablename__ = "documents"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    # File info
    original_filename = Column(String(512), nullable=True)
    storage_key = Column(String(512), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)

    # Classification
    doc_type = Column(String(30), default="unknown", index=True)
    classification_confidence = Column(Float, default=0.0)
    status = Column(String(20), default="uploaded")

    # OCR
    ocr_text = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    page_count = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    case = relationship("Case", back_populates="documents")
    processing_jobs = relationship("DocumentProcessingJob", back_populates="document", cascade="all, delete-orphan")


class DocumentProcessingJob(Base):
    """Persistent queue jobs for asynchronous OCR and document classification."""
    __tablename__ = "document_processing_jobs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued", index=True)  # queued | processing | completed | failed
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("Case", back_populates="document_processing_jobs")
    document = relationship("Document", back_populates="processing_jobs")


class ExtractedField(Base):
    """Stores individual extracted fields from documents."""
    __tablename__ = "extracted_fields"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Field metadata
    field_name = Column(String(100), nullable=False, index=True)
    field_value = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    source = Column(String(20), nullable=False, default="extraction")  # "extraction" | "manual" | "computed"

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    case = relationship("Case", back_populates="extracted_fields")


class BorrowerFeature(Base):
    """Stores the assembled borrower feature vector for a case."""
    __tablename__ = "borrower_features"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Identity
    full_name = Column(String(255), nullable=True)
    pan_number = Column(String(10), nullable=True, index=True)
    aadhaar_number = Column(String(12), nullable=True)
    dob = Column(DateTime(timezone=True), nullable=True)

    # Business
    entity_type = Column(String(20), nullable=True)
    business_vintage_years = Column(Float, nullable=True)
    gstin = Column(String(15), nullable=True, index=True)
    industry_type = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)

    # Financial
    annual_turnover = Column(Float, nullable=True)
    avg_monthly_balance = Column(Float, nullable=True)
    monthly_credit_avg = Column(Float, nullable=True)
    monthly_turnover = Column(Float, nullable=True)  # Average monthly credits (same as monthly_credit_avg)
    emi_outflow_monthly = Column(Float, nullable=True)
    bounce_count_12m = Column(Integer, nullable=True)
    cash_deposit_ratio = Column(Float, nullable=True)
    itr_total_income = Column(Float, nullable=True)

    # Credit
    cibil_score = Column(Integer, nullable=True, index=True)
    active_loan_count = Column(Integer, nullable=True)
    overdue_count = Column(Integer, nullable=True)
    enquiry_count_6m = Column(Integer, nullable=True)

    # Meta
    feature_completeness = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    case = relationship("Case", back_populates="borrower_features")


class WhatsAppMessage(Base):
    """Stores WhatsApp messages for per-case chat integration."""
    __tablename__ = "whatsapp_messages"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    # Message details
    message_id = Column(String(100), nullable=True, index=True)
    from_number = Column(String(20), nullable=False, index=True)
    to_number = Column(String(20), nullable=False)
    message_type = Column(String(20), default="text")  # text, image, document, audio, video
    message_body = Column(Text, nullable=True)
    media_url = Column(Text, nullable=True)

    # Direction
    direction = Column(String(10), nullable=False)  # inbound, outbound

    # Status
    status = Column(String(20), default="sent")  # sent, delivered, read, failed

    # Timestamps
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
