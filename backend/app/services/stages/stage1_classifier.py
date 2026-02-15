"""
Stage 1: Document Classification Service - IMPROVED VERSION
Two-layer approach with filename hints: ML model + keyword-based + filename matching
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
    method: str  # "ml", "keyword", "filename", "hybrid"
    scores: Dict[str, float] = None  # Debug info: scores for all categories


# ═══════════════════════════════════════════════════════════════
# FILENAME PATTERNS (STRONG SIGNALS)
# ═══════════════════════════════════════════════════════════════

FILENAME_PATTERNS = {
    DocumentType.BANK_STATEMENT: [
        r"(?i)(account?_?statement|acct_?stat|bank_?stat|statement.*account)",
        r"(?i)(hdfc|icici|sbi|axis|kotak|pnb|bob|idbi).*statement",
        r"(?i)statement.*\d{4,}",  # Statement with account number
    ],
    DocumentType.GST_RETURNS: [
        r"(?i)gstr[-_]?[139]b?",  # GSTR-1, GSTR-3B, GSTR-9
        r"(?i)gst.*return",
        r"(?i)gstr",
    ],
    DocumentType.GST_CERTIFICATE: [
        r"(?i)gst.*cert",
        r"(?i)gstin",
        r"(?i)gst.*registration",
        # Handles generic filenames like GST.pdf
        r"(?i)(^|[^a-z])gst([^a-z]|$)",
    ],
    DocumentType.UDYAM_SHOP_LICENSE: [
        r"(?i)udyam",
        r"(?i)msme.*cert",
        r"(?i)shop.*license",
    ],
    DocumentType.PAN_PERSONAL: [
        r"(?i)pan.*card",
        r"(?i)permanent.*account",
    ],
    DocumentType.AADHAAR: [
        r"(?i)aa?dh?aa?r",
        r"(?i)uid",
    ],
    DocumentType.CIBIL_REPORT: [
        r"(?i)cibil",
        r"(?i)credit.*report",
        r"(?i)transunion",
    ],
    DocumentType.ITR: [
        r"(?i)itr[-_]?\d",
        r"(?i)income.*tax.*return",
    ],
}


# ═══════════════════════════════════════════════════════════════
# IMPROVED KEYWORD PATTERNS
# ═══════════════════════════════════════════════════════════════

KEYWORD_PATTERNS = {
    DocumentType.AADHAAR: {
        "keywords": [
            r"(?i)UIDAI",
            r"(?i)Unique\s+Identification",
            r"(?i)Aa?dh?aa?r",
            r"(?i)enrolment",
            r"आधार",
            r"(?i)Government\s+of\s+India",
            r"(?i)Date\s+of\s+Birth|DOB",
            r"(?i)Address.*PIN",
            r"\d{4}\s+\d{4}\s+\d{4}",  # Aadhaar number pattern
            r"(?i)male|female",  # Gender field
        ],
        "threshold": 0.40,  # Lowered from 0.80
    },
    DocumentType.PAN_PERSONAL: {
        "keywords": [
            r"(?i)Permanent\s+Account\s+Number",
            r"(?i)Income\s+Tax\s+Department",
            r"(?i)NSDL",
            r"[A-Z]{5}\d{4}[A-Z]",  # PAN pattern
            r"(?i)Father'?s\s+Name",
            r"(?i)Signature",
            r"(?i)Date\s+of\s+Birth",
        ],
        "threshold": 0.40,  # Lowered from 0.80
    },
    DocumentType.PAN_BUSINESS: {
        "keywords": [
            r"(?i)Permanent\s+Account\s+Number",
            r"(?i)Income\s+Tax\s+Department",
            r"(?i)NSDL",
            r"[A-Z]{5}\d{4}[A-Z]",  # PAN pattern
            r"(?i)(Pvt\.?\s+Ltd|Private\s+Limited|LLP|Partnership|Proprietorship)",
            r"(?i)(Company|Firm|Business|Enterprise)",
        ],
        "threshold": 0.40,  # Lowered from 0.80
    },
    DocumentType.GST_CERTIFICATE: {
        "keywords": [
            r"(?i)GSTIN",
            r"(?i)Goods\s+and\s+Services\s+Tax",
            r"(?i)Certificate\s+of\s+Registration",
            r"(?i)GST\s+Registration",
            r"(?i)Tax\s+Payer",
            r"\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}",  # GSTIN pattern
            r"(?i)Date\s+of\s+(Registration|Liability)",
            r"(?i)State\s+Code",
        ],
        "threshold": 0.40,  # Lowered from 0.80
    },
    DocumentType.GST_RETURNS: {
        "keywords": [
            r"(?i)GSTR[-\s]?[139]B?",  # GSTR-1, GSTR-3B, GSTR-9
            r"(?i)taxable\s+value",
            r"(?i)CGST",
            r"(?i)SGST",
            r"(?i)IGST",
            r"(?i)Return\s+Period",
            r"(?i)Filing\s+Status",
            r"(?i)Tax\s+(Amount|Liability)",
            r"(?i)Input\s+Tax\s+Credit",
            r"(?i)Form\s+GSTR",
        ],
        "threshold": 0.35,  # Lowered from 0.85
    },
    DocumentType.BANK_STATEMENT: {
        "keywords": [
            r"(?i)Opening\s+Balance",
            r"(?i)Closing\s+Balance",
            r"(?i)Statement\s+of\s+Account",
            r"(?i)Transaction",
            r"(?i)\b(debit|credit|dr\.?|cr\.?)\b",
            r"(?i)(HDFC|ICICI|SBI|State\s+Bank|Axis|Kotak|PNB|Bank\s+of|IDBI|YES\s+Bank)",
            r"(?i)Account\s+(Number|No\.?)",
            r"(?i)IFSC",
            r"(?i)Branch",
            r"(?i)\b(withdrawal|deposit)\b",
            r"(?i)Balance",
        ],
        "threshold": 0.35,  # Lowered from 0.85
    },
    DocumentType.ITR: {
        "keywords": [
            r"(?i)Assessment\s+Year",
            r"(?i)Total\s+Income",
            r"(?i)ITR[-\s]?\d",
            r"(?i)Income\s+Tax\s+Return",
            r"(?i)Verification",
            r"(?i)Acknowledgement\s+Number",
            r"(?i)Tax\s+Payable",
            r"(?i)Gross\s+Total\s+Income",
            r"(?i)Deductions",
            r"(?i)PAN",
            r"(?i)Financial\s+Year",
        ],
        "threshold": 0.40,  # Lowered from 0.80
    },
    DocumentType.FINANCIAL_STATEMENTS: {
        "keywords": [
            r"(?i)Balance\s+Sheet",
            r"(?i)Profit\s+(and|&)\s+Loss",
            r"(?i)Schedule",
            r"(?i)Audit\s+Report",
            r"(?i)Auditor",
            r"(?i)\b(Assets|Liabilities)\b",
            r"(?i)Equity",
            r"(?i)\b(Revenue|Expenditure)\b",
            r"(?i)Financial\s+(Year|Statement)",
            r"(?i)Chartered\s+Accountant",
        ],
        "threshold": 0.40,  # Lowered from 0.75
    },
    DocumentType.CIBIL_REPORT: {
        "keywords": [
            r"(?i)TransUnion",
            r"(?i)Credit\s+Score",
            r"(?i)Credit\s+Information",
            r"(?i)CIBIL",
            r"(?i)Account\s+Summary",
            r"(?i)Enquir(y|ies)",
            r"(?i)Credit\s+History",
            r"(?i)Score\s+Factors",
            r"(?i)Bureau",
        ],
        "threshold": 0.40,  # Lowered from 0.85
    },
    DocumentType.UDYAM_SHOP_LICENSE: {
        "keywords": [
            r"(?i)Udyam\s+Registration",
            r"(?i)MSME",
            r"(?i)Shop\s+(and|&)\s+Establishment",
            r"(?i)License",
            r"(?i)Micro,?\s+Small\s+(and|&)\s+Medium\s+Enterprise",
            r"(?i)Registration\s+(Number|Certificate)",
            r"(?i)Udyam",
            r"(?i)Ministry.*MSME",
        ],
        "threshold": 0.40,  # Lowered from 0.75
    },
    DocumentType.PROPERTY_DOCUMENTS: {
        "keywords": [
            r"(?i)Sale\s+Deed",
            r"(?i)Registry",
            r"(?i)Property\s+Tax",
            r"(?i)Conveyance",
            r"(?i)Sub-Registrar",
            r"(?i)Plot\s+No",
            r"(?i)Survey\s+Number",
            r"(?i)Property\s+(No|Number)",
            r"(?i)Stamp\s+Duty",
            r"(?i)Registration\s+Fee",
        ],
        "threshold": 0.40,  # Lowered from 0.70
    },
}


# ═══════════════════════════════════════════════════════════════
# IMPROVED DOCUMENT CLASSIFIER
# ═══════════════════════════════════════════════════════════════

class DocumentClassifier:
    """
    Three-layer document classifier:
    1. Filename-based hints (strongest signal)
    2. ML-based (TF-IDF + Logistic Regression) - when model available
    3. Keyword/rule-based fallback - always available
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

    def classify(self, ocr_text: str, filename: Optional[str] = None) -> ClassificationResult:
        """
        Classify a document based on its OCR text and optionally filename.

        Args:
            ocr_text: The OCR extracted text from the document
            filename: Optional filename for additional hints

        Returns:
            ClassificationResult with doc_type, confidence, and method
        """
        # Step 1: Try filename-based classification (strongest signal)
        if filename:
            filename_result = self._classify_from_filename(filename)
            if filename_result and filename_result.confidence >= 0.90:
                # High confidence from filename alone
                return filename_result

        # Check if we have sufficient OCR text
        if not ocr_text or len(ocr_text.strip()) < 10:
            # If no good OCR but we have filename hint, use it
            if filename:
                filename_result = self._classify_from_filename(filename)
                if filename_result and filename_result.confidence >= 0.60:
                    return filename_result

            return ClassificationResult(
                doc_type=DocumentType.UNKNOWN,
                confidence=0.0,
                method="empty_input"
            )

        # Step 2: Try ML classification if available
        ml_result = None
        if self.ml_available:
            ml_result = self._classify_with_ml(ocr_text)
            if ml_result and ml_result.confidence >= 0.75:
                return ml_result

        # Step 3: Keyword-based classification
        keyword_result = self._classify_with_keywords(ocr_text)

        # Step 4: Hybrid approach - combine filename + keyword/ML scores
        if filename:
            filename_result = self._classify_from_filename(filename)
            if filename_result:
                # If filename and keyword agree, boost confidence
                if filename_result.doc_type == keyword_result.doc_type:
                    combined_confidence = min(
                        0.95,
                        (filename_result.confidence * 0.6 + keyword_result.confidence * 0.4)
                    )
                    return ClassificationResult(
                        doc_type=keyword_result.doc_type,
                        confidence=combined_confidence,
                        method="hybrid",
                        scores=keyword_result.scores
                    )
                # If filename has higher confidence, use it
                elif filename_result.confidence > keyword_result.confidence + 0.20:
                    return filename_result

        # Return best result (ML or keyword)
        if ml_result and ml_result.confidence > keyword_result.confidence:
            return ml_result

        return keyword_result

    def _classify_from_filename(self, filename: str) -> Optional[ClassificationResult]:
        """Classify based on filename patterns."""
        if not filename:
            return None

        scores = {}

        for doc_type, patterns in FILENAME_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename):
                    # Filename match is a strong signal
                    scores[doc_type.value] = 0.90
                    break

            if doc_type.value not in scores:
                scores[doc_type.value] = 0.0

        # Find best match
        best_type = None
        best_score = 0.0

        for doc_type_str, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = doc_type_str

        if best_type and best_score >= 0.60:
            return ClassificationResult(
                doc_type=DocumentType(best_type),
                confidence=float(best_score),
                method="filename",
                scores=scores
            )

        return None

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
            # Fallback to keyword/filename classifiers if ML pipeline is unavailable.
            return None

    def _classify_with_keywords(self, ocr_text: str) -> ClassificationResult:
        """Classify using keyword matching (fallback method) - IMPROVED."""
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
                r"(?i)(Pvt\.?\s+Ltd|Private\s+Limited|LLP|Partnership|Proprietorship|Company|Firm)",
                ocr_text
            )
            if business_indicators:
                # Boost business PAN score
                scores[DocumentType.PAN_BUSINESS.value] = max(
                    scores.get(DocumentType.PAN_BUSINESS.value, 0),
                    scores.get(DocumentType.PAN_PERSONAL.value, 0) + 0.1
                )
                scores[DocumentType.PAN_PERSONAL.value] = 0
            else:
                # Boost personal PAN score
                scores[DocumentType.PAN_PERSONAL.value] = max(
                    scores.get(DocumentType.PAN_PERSONAL.value, 0),
                    scores.get(DocumentType.PAN_BUSINESS.value, 0) + 0.1
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


# ═══════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

# Global classifier instance (singleton pattern)
_classifier_instance: Optional[DocumentClassifier] = None


def get_classifier() -> DocumentClassifier:
    """Get the global classifier instance (singleton)."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = DocumentClassifier()
    return _classifier_instance


def classify_document(ocr_text: str, filename: Optional[str] = None) -> ClassificationResult:
    """
    Classify a document (convenience function).

    Args:
        ocr_text: OCR extracted text
        filename: Optional filename for additional hints

    Returns:
        ClassificationResult
    """
    classifier = get_classifier()
    return classifier.classify(ocr_text, filename)
