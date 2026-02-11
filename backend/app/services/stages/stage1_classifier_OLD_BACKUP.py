"""
Stage 1: Document Classification Service
Two-layer approach: ML model (when available) + keyword-based fallback
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
import re
import os
import joblib
from pathlib import Path

from app.core.enums import DocumentType


@dataclass
class ClassificationResult:
    """Result of document classification."""
    doc_type: DocumentType
    confidence: float  # 0-1
    method: str  # "ml" or "keyword"
    scores: Dict[str, float] = None  # Debug info: scores for all categories


# ─── Keyword Dictionaries for Each Document Type ─────────────────────────────
KEYWORD_PATTERNS = {
    DocumentType.AADHAAR: {
        "keywords": [
            r"UIDAI",
            r"Unique\s+Identification",
            r"Aadhaar",
            r"enrolment",
            r"आधार",
            r"Government\s+of\s+India",
            r"Date\s+of\s+Birth",
            r"Address.*PIN",
            r"\d{4}\s+\d{4}\s+\d{4}",  # Aadhaar number pattern
        ],
        "threshold": 0.80,
    },
    DocumentType.PAN_PERSONAL: {
        "keywords": [
            r"Permanent\s+Account\s+Number",
            r"Income\s+Tax\s+Department",
            r"NSDL",
            r"[A-Z]{5}\d{4}[A-Z]",  # PAN pattern
            r"Father's\s+Name",
            r"Signature",
        ],
        "threshold": 0.80,
    },
    DocumentType.PAN_BUSINESS: {
        "keywords": [
            r"Permanent\s+Account\s+Number",
            r"Income\s+Tax\s+Department",
            r"NSDL",
            r"[A-Z]{5}\d{4}[A-Z]",  # PAN pattern
            r"(Pvt\.?\s+Ltd|Private\s+Limited|LLP|Partnership|Proprietorship)",
            r"(Company|Firm|Business)",
        ],
        "threshold": 0.80,
    },
    DocumentType.GST_CERTIFICATE: {
        "keywords": [
            r"GSTIN",
            r"Goods\s+and\s+Services\s+Tax",
            r"Certificate\s+of\s+Registration",
            r"GST\s+Registration",
            r"Tax\s+Payer",
            r"\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}",  # GSTIN pattern
            r"Date\s+of\s+Registration",
        ],
        "threshold": 0.80,
    },
    DocumentType.GST_RETURNS: {
        "keywords": [
            r"GSTR",
            r"taxable\s+value",
            r"CGST",
            r"SGST",
            r"IGST",
            r"Return\s+Period",
            r"Filing\s+Status",
            r"Tax\s+Amount",
            r"(GSTR-1|GSTR-3B|GSTR-9)",
        ],
        "threshold": 0.85,
    },
    DocumentType.BANK_STATEMENT: {
        "keywords": [
            r"Opening\s+Balance",
            r"Closing\s+Balance",
            r"Statement\s+of\s+Account",
            r"Transaction",
            r"debit",
            r"credit",
            r"(HDFC|ICICI|SBI|Axis|Kotak|PNB|Bank\s+of)",
            r"Account\s+Number",
            r"IFSC",
            r"Branch",
        ],
        "threshold": 0.85,
    },
    DocumentType.ITR: {
        "keywords": [
            r"Assessment\s+Year",
            r"Total\s+Income",
            r"ITR-\d",
            r"Income\s+Tax\s+Return",
            r"Verification",
            r"Acknowledgement\s+Number",
            r"Tax\s+Payable",
            r"Gross\s+Total\s+Income",
            r"Deductions",
        ],
        "threshold": 0.80,
    },
    DocumentType.FINANCIAL_STATEMENTS: {
        "keywords": [
            r"Balance\s+Sheet",
            r"Profit\s+and\s+Loss",
            r"Schedule",
            r"Audit\s+Report",
            r"Auditor",
            r"Assets",
            r"Liabilities",
            r"Equity",
            r"Revenue",
            r"Expenditure",
            r"Financial\s+Year",
        ],
        "threshold": 0.75,
    },
    DocumentType.CIBIL_REPORT: {
        "keywords": [
            r"TransUnion",
            r"Credit\s+Score",
            r"Credit\s+Information",
            r"CIBIL",
            r"Account\s+Summary",
            r"Enquiry",
            r"Credit\s+History",
            r"Score\s+Factors",
        ],
        "threshold": 0.85,
    },
    DocumentType.UDYAM_SHOP_LICENSE: {
        "keywords": [
            r"Udyam\s+Registration",
            r"MSME",
            r"Shop\s+and\s+Establishment",
            r"License",
            r"Micro,?\s+Small\s+(and|&)\s+Medium\s+Enterprise",
            r"Registration\s+Number",
            r"Udyam",
        ],
        "threshold": 0.75,
    },
    DocumentType.PROPERTY_DOCUMENTS: {
        "keywords": [
            r"Sale\s+Deed",
            r"Registry",
            r"Property\s+Tax",
            r"Conveyance",
            r"Sub-Registrar",
            r"Plot\s+No",
            r"Survey\s+Number",
            r"Property\s+No",
            r"Stamp\s+Duty",
            r"Registration\s+Fee",
        ],
        "threshold": 0.70,
    },
}

# Confidence thresholds for ML predictions
ML_CONFIDENCE_THRESHOLDS = {
    DocumentType.AADHAAR: 0.80,
    DocumentType.PAN_PERSONAL: 0.80,
    DocumentType.PAN_BUSINESS: 0.80,
    DocumentType.GST_CERTIFICATE: 0.80,
    DocumentType.GST_RETURNS: 0.85,
    DocumentType.BANK_STATEMENT: 0.85,
    DocumentType.ITR: 0.80,
    DocumentType.FINANCIAL_STATEMENTS: 0.75,
    DocumentType.CIBIL_REPORT: 0.85,
    DocumentType.UDYAM_SHOP_LICENSE: 0.75,
    DocumentType.PROPERTY_DOCUMENTS: 0.70,
}


class DocumentClassifier:
    """
    Two-layer document classifier:
    1. ML-based (TF-IDF + Logistic Regression) - when model available
    2. Keyword/rule-based fallback - always available
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize the classifier.

        Args:
            model_path: Path to the trained model directory (default: backend/models/)
        """
        self.model = None
        self.vectorizer = None
        self.ml_available = False

        # Set default model path
        if model_path is None:
            backend_dir = Path(__file__).parent.parent.parent.parent
            model_path = backend_dir / "models"

        self.model_path = Path(model_path)
        self._load_ml_model()

    def _load_ml_model(self) -> bool:
        """Load the ML model if available."""
        try:
            model_file = self.model_path / "classifier_model.joblib"
            vectorizer_file = self.model_path / "classifier_vectorizer.joblib"

            if model_file.exists() and vectorizer_file.exists():
                self.model = joblib.load(model_file)
                self.vectorizer = joblib.load(vectorizer_file)
                self.ml_available = True
                print(f"✓ ML classifier model loaded from {self.model_path}")
                return True
            else:
                print(f"⚠ ML model not found at {self.model_path}. Using keyword-based fallback.")
                return False
        except Exception as e:
            print(f"⚠ Error loading ML model: {e}. Using keyword-based fallback.")
            return False

    def classify(self, ocr_text: str) -> ClassificationResult:
        """
        Classify a document based on its OCR text.

        Args:
            ocr_text: The OCR extracted text from the document

        Returns:
            ClassificationResult with doc_type, confidence, and method
        """
        if not ocr_text or len(ocr_text.strip()) < 10:
            return ClassificationResult(
                doc_type=DocumentType.UNKNOWN,
                confidence=0.0,
                method="empty_input"
            )

        # Try ML classification first if available
        if self.ml_available:
            ml_result = self._classify_with_ml(ocr_text)
            # Use ML result if confidence is high enough
            if ml_result and ml_result.confidence >= 0.70:
                return ml_result

        # Fallback to keyword-based classification
        return self._classify_with_keywords(ocr_text)

    def _classify_with_ml(self, ocr_text: str) -> Optional[ClassificationResult]:
        """Classify using ML model (TF-IDF + Logistic Regression)."""
        try:
            # Vectorize the text
            text_vectorized = self.vectorizer.transform([ocr_text])

            # Get prediction and probabilities
            prediction = self.model.predict(text_vectorized)[0]
            probabilities = self.model.predict_proba(text_vectorized)[0]

            # Get the confidence for the predicted class
            confidence = max(probabilities)

            # Convert prediction to DocumentType
            try:
                doc_type = DocumentType(prediction)
            except ValueError:
                doc_type = DocumentType.UNKNOWN

            # Get all class probabilities for debugging
            scores = {
                self.model.classes_[i]: float(prob)
                for i, prob in enumerate(probabilities)
            }

            return ClassificationResult(
                doc_type=doc_type,
                confidence=float(confidence),
                method="ml",
                scores=scores
            )
        except Exception as e:
            print(f"Error in ML classification: {e}")
            return None

    def _classify_with_keywords(self, ocr_text: str) -> ClassificationResult:
        """Classify using keyword matching (fallback method)."""
        # Normalize text for better matching
        text_lower = ocr_text.lower()

        scores = {}

        # Calculate score for each document type
        for doc_type, config in KEYWORD_PATTERNS.items():
            keywords = config["keywords"]
            matched_count = 0

            for pattern in keywords:
                # Case-insensitive regex search
                if re.search(pattern, ocr_text, re.IGNORECASE):
                    matched_count += 1

            # Calculate score as percentage of matched keywords
            score = matched_count / len(keywords) if keywords else 0
            scores[doc_type.value] = score

        # Special handling for PAN - distinguish between personal and business
        if scores.get(DocumentType.PAN_PERSONAL.value, 0) > 0 or \
           scores.get(DocumentType.PAN_BUSINESS.value, 0) > 0:
            # Check for business indicators
            business_indicators = re.search(
                r"(Pvt\.?\s+Ltd|Private\s+Limited|LLP|Partnership|Proprietorship|Company|Firm)",
                ocr_text,
                re.IGNORECASE
            )
            if business_indicators:
                # Boost business PAN score
                scores[DocumentType.PAN_BUSINESS.value] = max(
                    scores.get(DocumentType.PAN_BUSINESS.value, 0),
                    scores.get(DocumentType.PAN_PERSONAL.value, 0)
                )
                scores[DocumentType.PAN_PERSONAL.value] = 0
            else:
                # Boost personal PAN score
                scores[DocumentType.PAN_PERSONAL.value] = max(
                    scores.get(DocumentType.PAN_PERSONAL.value, 0),
                    scores.get(DocumentType.PAN_BUSINESS.value, 0)
                )
                scores[DocumentType.PAN_BUSINESS.value] = 0

        # Find the best match
        best_type = None
        best_score = 0.0

        for doc_type_str, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = doc_type_str

        # Check if score meets threshold
        if best_type:
            doc_type = DocumentType(best_type)
            threshold = KEYWORD_PATTERNS[doc_type]["threshold"]

            if best_score >= threshold:
                return ClassificationResult(
                    doc_type=doc_type,
                    confidence=float(best_score),
                    method="keyword",
                    scores=scores
                )

        # If no match above threshold, return UNKNOWN
        return ClassificationResult(
            doc_type=DocumentType.UNKNOWN,
            confidence=float(best_score) if best_score > 0 else 0.0,
            method="keyword",
            scores=scores
        )


# ─── Convenience Functions ────────────────────────────────────────────────────

# Global classifier instance (singleton pattern)
_classifier_instance: Optional[DocumentClassifier] = None


def get_classifier() -> DocumentClassifier:
    """Get the global classifier instance (singleton)."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = DocumentClassifier()
    return _classifier_instance


def classify_document(ocr_text: str) -> ClassificationResult:
    """
    Convenience function to classify a document.

    Args:
        ocr_text: The OCR extracted text

    Returns:
        ClassificationResult
    """
    classifier = get_classifier()
    return classifier.classify(ocr_text)
