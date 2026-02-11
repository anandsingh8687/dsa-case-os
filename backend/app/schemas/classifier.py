"""Pydantic schemas for document classification."""
from pydantic import BaseModel, Field
from typing import Optional, Dict
from app.core.enums import DocumentType


class ClassificationResultSchema(BaseModel):
    """Classification result schema."""
    doc_type: DocumentType
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence (0-1)")
    method: str = Field(..., description="Classification method: 'ml' or 'keyword'")
    scores: Optional[Dict[str, float]] = Field(None, description="Debug: scores for all categories")

    class Config:
        json_schema_extra = {
            "example": {
                "doc_type": "aadhaar",
                "confidence": 0.95,
                "method": "ml",
                "scores": {
                    "aadhaar": 0.95,
                    "pan_personal": 0.03,
                    "bank_statement": 0.02
                }
            }
        }


class ReclassifyRequest(BaseModel):
    """Request schema for manual reclassification."""
    doc_type: DocumentType = Field(..., description="Manually assigned document type")
    confidence: Optional[float] = Field(1.0, ge=0.0, le=1.0, description="Confidence (default: 1.0 for manual)")

    class Config:
        json_schema_extra = {
            "example": {
                "doc_type": "pan_personal",
                "confidence": 1.0
            }
        }
