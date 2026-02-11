"""Stage 2: Field Extraction Service
Extracts structured fields from OCR text using regex patterns and anchor keywords.
Implements validation rules and confidence scoring.
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app.schemas.shared import ExtractedFieldItem
from app.core.enums import DocumentType

logger = logging.getLogger(__name__)


# Indian state code mapping for GSTIN validation
GSTIN_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman and Diu", "26": "Dadra and Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh"
}


class FieldExtractor:
    """Handles regex-based field extraction from OCR text."""

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize the field extractor.

        Args:
            confidence_threshold: Minimum confidence for accepting extracted values (0-1)
        """
        self.confidence_threshold = confidence_threshold

    async def extract_fields(
        self,
        ocr_text: str,
        doc_type: DocumentType
    ) -> List[ExtractedFieldItem]:
        """
        Extract fields from OCR text based on document type.

        Args:
            ocr_text: Raw OCR text from document
            doc_type: Type of document being processed

        Returns:
            List of extracted field items with confidence scores
        """
        if not ocr_text or not ocr_text.strip():
            logger.warning(f"Empty OCR text for document type {doc_type}")
            return []

        # Route to appropriate extraction method
        extractor_map = {
            DocumentType.PAN_PERSONAL: self._extract_pan_card,
            DocumentType.PAN_BUSINESS: self._extract_pan_card,
            DocumentType.AADHAAR: self._extract_aadhaar,
            DocumentType.GST_CERTIFICATE: self._extract_gst_certificate,
            DocumentType.GST_RETURNS: self._extract_gst_returns,
            DocumentType.CIBIL_REPORT: self._extract_cibil_report,
            DocumentType.ITR: self._extract_itr,
            DocumentType.FINANCIAL_STATEMENTS: self._extract_financial_statements,
        }

        extractor = extractor_map.get(doc_type)
        if not extractor:
            logger.info(f"No extractor implemented for document type {doc_type}")
            return []

        try:
            fields = extractor(ocr_text)
            # Validate and adjust confidence
            validated_fields = []
            for field in fields:
                if self._validate_field(field):
                    validated_fields.append(field)
                else:
                    # Lower confidence for invalid fields but still keep them
                    field.confidence = field.confidence * 0.5
                    validated_fields.append(field)

            return validated_fields
        except Exception as e:
            logger.error(f"Error extracting fields from {doc_type}: {str(e)}", exc_info=True)
            return []

    def _extract_pan_card(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from PAN card."""
        fields = []

        # PAN number: [A-Z]{5}[0-9]{4}[A-Z]
        pan_pattern = r'\b([A-Z]{5}[0-9]{4}[A-Z])\b'
        pan_match = re.search(pan_pattern, ocr_text)
        if pan_match:
            pan_number = pan_match.group(1)
            # Validate PAN structure
            confidence = 0.9 if self._validate_pan(pan_number) else 0.6
            fields.append(ExtractedFieldItem(
                field_name="pan_number",
                field_value=pan_number,
                confidence=confidence,
                source="extraction"
            ))

        # Name: Look for text near "Name" keyword
        name_pattern = r'(?:Name|NAME|name)\s*[:\-]?\s*([A-Z][A-Za-z\s]{2,50})'
        name_match = re.search(name_pattern, ocr_text)
        if name_match:
            name = name_match.group(1).strip()
            fields.append(ExtractedFieldItem(
                field_name="full_name",
                field_value=name,
                confidence=0.75,
                source="extraction"
            ))

        # Date of Birth: dd/mm/yyyy or dd-mm-yyyy
        dob_pattern = r'(?:Date of Birth|DOB|Birth|dob)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'
        dob_match = re.search(dob_pattern, ocr_text, re.IGNORECASE)
        if dob_match:
            dob = dob_match.group(1).replace('-', '/')
            fields.append(ExtractedFieldItem(
                field_name="dob",
                field_value=dob,
                confidence=0.8,
                source="extraction"
            ))

        return fields

    def _extract_aadhaar(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from Aadhaar card."""
        fields = []

        # Aadhaar number: 12 digits, may have spaces
        aadhaar_pattern = r'\b(\d{4}\s?\d{4}\s?\d{4})\b'
        aadhaar_match = re.search(aadhaar_pattern, ocr_text)
        if aadhaar_match:
            aadhaar = aadhaar_match.group(1).replace(' ', '')
            if len(aadhaar) == 12:
                fields.append(ExtractedFieldItem(
                    field_name="aadhaar_number",
                    field_value=aadhaar,
                    confidence=0.85,
                    source="extraction"
                ))

        # Name: First prominent capitalized name
        name_pattern = r'(?:Name|NAME|name)\s*[:\-]?\s*([A-Z][A-Za-z\s]{2,50})'
        name_match = re.search(name_pattern, ocr_text)
        if name_match:
            name = name_match.group(1).strip()
            fields.append(ExtractedFieldItem(
                field_name="full_name",
                field_value=name,
                confidence=0.75,
                source="extraction"
            ))
        else:
            # Try to find first prominent capitalized text (fallback)
            fallback_name_pattern = r'\b([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b'
            fallback_match = re.search(fallback_name_pattern, ocr_text)
            if fallback_match:
                name = fallback_match.group(1)
                fields.append(ExtractedFieldItem(
                    field_name="full_name",
                    field_value=name,
                    confidence=0.55,
                    source="extraction"
                ))

        # DOB
        dob_pattern = r'(?:DOB|Birth|dob|Year of Birth)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'
        dob_match = re.search(dob_pattern, ocr_text, re.IGNORECASE)
        if dob_match:
            dob = dob_match.group(1).replace('-', '/')
            fields.append(ExtractedFieldItem(
                field_name="dob",
                field_value=dob,
                confidence=0.8,
                source="extraction"
            ))

        # Address: Multi-line text after "Address"
        address_pattern = r'(?:Address|ADDRESS|address)\s*[:\-]?\s*([A-Za-z0-9\s,\.\-/]+(?:\n[A-Za-z0-9\s,\.\-/]+){0,3})'
        address_match = re.search(address_pattern, ocr_text)
        if address_match:
            address = address_match.group(1).strip()
            fields.append(ExtractedFieldItem(
                field_name="address",
                field_value=address,
                confidence=0.65,
                source="extraction"
            ))

        return fields

    def _extract_gst_certificate(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from GST certificate."""
        fields = []

        # GSTIN: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9][A-Z][0-9A-Z]
        gstin_pattern = r'\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z][0-9A-Z])\b'
        gstin_match = re.search(gstin_pattern, ocr_text)
        if gstin_match:
            gstin = gstin_match.group(1)
            confidence = 0.9 if self._validate_gstin(gstin) else 0.6
            fields.append(ExtractedFieldItem(
                field_name="gstin",
                field_value=gstin,
                confidence=confidence,
                source="extraction"
            ))

            # Extract state from GSTIN
            state_code = gstin[:2]
            state_name = GSTIN_STATE_CODES.get(state_code)
            if state_name:
                fields.append(ExtractedFieldItem(
                    field_name="state",
                    field_value=state_name,
                    confidence=0.95,
                    source="extraction"
                ))

        # Business name
        business_patterns = [
            r'(?:Legal Name|Trade Name|Business Name)\s*[:\-]?\s*([A-Z][A-Za-z0-9\s&\.\-]{2,100})',
            r'(?:Taxpayer Name|Name of Business)\s*[:\-]?\s*([A-Z][A-Za-z0-9\s&\.\-]{2,100})'
        ]
        for pattern in business_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                business_name = match.group(1).strip()
                fields.append(ExtractedFieldItem(
                    field_name="business_name",
                    field_value=business_name,
                    confidence=0.8,
                    source="extraction"
                ))
                break

        # Registration date
        reg_date_pattern = r'(?:Date of Registration|Registration Date)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'
        reg_date_match = re.search(reg_date_pattern, ocr_text, re.IGNORECASE)
        if reg_date_match:
            reg_date = reg_date_match.group(1).replace('-', '/')
            fields.append(ExtractedFieldItem(
                field_name="gst_registration_date",
                field_value=reg_date,
                confidence=0.8,
                source="extraction"
            ))

        return fields

    def _extract_gst_returns(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from GST returns."""
        fields = []

        # Total taxable value
        taxable_patterns = [
            r'(?:Total Taxable Value|Taxable Value)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r'(?:Total Invoice Value|Invoice Value)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        ]
        for pattern in taxable_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                value = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="gst_taxable_value",
                    field_value=value,
                    confidence=0.75,
                    source="extraction"
                ))
                break

        # CGST amount
        cgst_pattern = r'(?:CGST|Central GST)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        cgst_match = re.search(cgst_pattern, ocr_text, re.IGNORECASE)
        if cgst_match:
            cgst = cgst_match.group(1).replace(',', '')
            fields.append(ExtractedFieldItem(
                field_name="gst_cgst_amount",
                field_value=cgst,
                confidence=0.75,
                source="extraction"
            ))

        # SGST amount
        sgst_pattern = r'(?:SGST|State GST)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        sgst_match = re.search(sgst_pattern, ocr_text, re.IGNORECASE)
        if sgst_match:
            sgst = sgst_match.group(1).replace(',', '')
            fields.append(ExtractedFieldItem(
                field_name="gst_sgst_amount",
                field_value=sgst,
                confidence=0.75,
                source="extraction"
            ))

        # Filing period: month/year
        period_patterns = [
            r'(?:Period|Tax Period|Return Period)\s*[:\-]?\s*(\d{2}[/-]\d{4})',
            r'(?:Month|Filing Month)\s*[:\-]?\s*([A-Za-z]+\s*\d{4})'
        ]
        for pattern in period_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                period = match.group(1)
                fields.append(ExtractedFieldItem(
                    field_name="gst_filing_period",
                    field_value=period,
                    confidence=0.7,
                    source="extraction"
                ))
                break

        return fields

    def _extract_cibil_report(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from CIBIL report."""
        fields = []

        # Credit score: 3-digit number (300-900)
        score_patterns = [
            r'(?:Score|CIBIL Score|Credit Score)\s*[:\-]?\s*(\d{3})',
            r'\b([3-9]\d{2})\b'  # Fallback: any 3-digit number in range
        ]
        for pattern in score_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                if 300 <= score <= 900:
                    fields.append(ExtractedFieldItem(
                        field_name="cibil_score",
                        field_value=str(score),
                        confidence=0.85,
                        source="extraction"
                    ))
                    break

        # Active loans count
        active_loan_pattern = r'(?:Active Accounts|Active Loans)\s*[:\-]?\s*(\d+)'
        active_match = re.search(active_loan_pattern, ocr_text, re.IGNORECASE)
        if active_match:
            count = active_match.group(1)
            fields.append(ExtractedFieldItem(
                field_name="active_loan_count",
                field_value=count,
                confidence=0.75,
                source="extraction"
            ))

        # Overdue accounts
        overdue_pattern = r'(?:Overdue|Delinquent|DPD)\s*[:\-]?\s*(\d+)'
        overdue_match = re.search(overdue_pattern, ocr_text, re.IGNORECASE)
        if overdue_match:
            count = overdue_match.group(1)
            fields.append(ExtractedFieldItem(
                field_name="overdue_count",
                field_value=count,
                confidence=0.75,
                source="extraction"
            ))

        # Enquiry count
        enquiry_pattern = r'(?:Enquiry|Enquiries|Credit Enquiries|Recent Enquiries)\s*[:\-]?\s*(\d+)'
        enquiry_match = re.search(enquiry_pattern, ocr_text, re.IGNORECASE)
        if enquiry_match:
            count = enquiry_match.group(1)
            fields.append(ExtractedFieldItem(
                field_name="enquiry_count_6m",
                field_value=count,
                confidence=0.7,
                source="extraction"
            ))

        return fields

    def _extract_itr(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from ITR (Income Tax Return)."""
        fields = []

        # Total income
        income_patterns = [
            r'(?:Total Income|Gross Total Income)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r'(?:Gross Total Income|GTI)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        ]
        for pattern in income_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                income = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="itr_total_income",
                    field_value=income,
                    confidence=0.8,
                    source="extraction"
                ))
                break

        # Assessment year
        ay_pattern = r'(?:Assessment Year|AY|A\.Y\.)\s*[:\-]?\s*(20\d{2}-\d{2})'
        ay_match = re.search(ay_pattern, ocr_text, re.IGNORECASE)
        if ay_match:
            ay = ay_match.group(1)
            fields.append(ExtractedFieldItem(
                field_name="itr_assessment_year",
                field_value=ay,
                confidence=0.85,
                source="extraction"
            ))

        # Tax paid
        tax_patterns = [
            r'(?:Tax Paid|Total Tax Paid|Tax Payment)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r'(?:Self Assessment Tax|Advance Tax)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        ]
        for pattern in tax_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                tax = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="itr_tax_paid",
                    field_value=tax,
                    confidence=0.75,
                    source="extraction"
                ))
                break

        # Business income
        business_income_pattern = r'(?:Income from Business|Business Income|Profits and Gains)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        business_match = re.search(business_income_pattern, ocr_text, re.IGNORECASE)
        if business_match:
            business_income = business_match.group(1).replace(',', '')
            fields.append(ExtractedFieldItem(
                field_name="itr_business_income",
                field_value=business_income,
                confidence=0.75,
                source="extraction"
            ))

        return fields

    def _extract_financial_statements(self, ocr_text: str) -> List[ExtractedFieldItem]:
        """Extract fields from financial statements (Balance Sheet, P&L)."""
        fields = []

        # Revenue / Sales
        revenue_patterns = [
            r'(?:Revenue|Total Revenue|Sales|Net Sales|Turnover)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r'(?:Total Income|Gross Revenue)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                revenue = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="annual_turnover",
                    field_value=revenue,
                    confidence=0.8,
                    source="extraction"
                ))
                break

        # Net profit
        profit_patterns = [
            r'(?:Net Profit|Profit After Tax|PAT|Net Income)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r'(?:Profit for the year|Net Earnings)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)'
        ]
        for pattern in profit_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                profit = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="net_profit",
                    field_value=profit,
                    confidence=0.75,
                    source="extraction"
                ))
                break

        # Net worth
        networth_patterns = [
            r'(?:Net Worth|Shareholders Fund|Shareholders Equity|Total Equity)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)',
            r"(?:Owner's Equity|Capital and Reserves)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([0-9,]+\.?\d*)"
        ]
        for pattern in networth_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                networth = match.group(1).replace(',', '')
                fields.append(ExtractedFieldItem(
                    field_name="net_worth",
                    field_value=networth,
                    confidence=0.75,
                    source="extraction"
                ))
                break

        return fields

    def _validate_pan(self, pan: str) -> bool:
        """
        Validate PAN number format and structure.
        4th character indicates entity type: P=Person, C=Company, F=Firm, etc.
        """
        if not pan or len(pan) != 10:
            return False

        # Check format
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            return False

        # 4th character should be P, C, F, H, A, T, B, L, J, G
        valid_entity_types = ['P', 'C', 'F', 'H', 'A', 'T', 'B', 'L', 'J', 'G']
        if pan[3] not in valid_entity_types:
            return False

        return True

    def _validate_gstin(self, gstin: str) -> bool:
        """
        Validate GSTIN format and state code.
        First 2 digits should be valid state code.
        """
        if not gstin or len(gstin) != 15:
            return False

        # Check format
        if not re.match(r'^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z][0-9A-Z]$', gstin):
            return False

        # Validate state code
        state_code = gstin[:2]
        if state_code not in GSTIN_STATE_CODES:
            return False

        # The PAN is embedded in GSTIN (positions 2-11)
        embedded_pan = gstin[2:12]
        if not self._validate_pan(embedded_pan):
            return False

        return True

    def _validate_field(self, field: ExtractedFieldItem) -> bool:
        """
        Validate extracted field based on field name and apply business rules.

        Returns:
            True if field is valid, False otherwise
        """
        if not field.field_value:
            return False

        # PAN validation
        if field.field_name == "pan_number":
            return self._validate_pan(field.field_value)

        # GSTIN validation
        if field.field_name == "gstin":
            return self._validate_gstin(field.field_value)

        # Aadhaar validation
        if field.field_name == "aadhaar_number":
            aadhaar = field.field_value.replace(' ', '')
            return len(aadhaar) == 12 and aadhaar.isdigit()

        # CIBIL score validation
        if field.field_name == "cibil_score":
            try:
                score = int(field.field_value)
                return 300 <= score <= 900
            except ValueError:
                return False

        # Date validation
        if field.field_name in ["dob", "gst_registration_date"]:
            try:
                # Try to parse date
                date_str = field.field_value.replace('-', '/')
                datetime.strptime(date_str, '%d/%m/%Y')
                return True
            except ValueError:
                return False

        # Numeric field validation
        numeric_fields = [
            "annual_turnover", "itr_total_income", "gst_taxable_value",
            "active_loan_count", "overdue_count", "enquiry_count_6m"
        ]
        if field.field_name in numeric_fields:
            try:
                value = float(field.field_value.replace(',', ''))
                return value >= 0
            except ValueError:
                return False

        # Default: field is valid
        return True


# Singleton instance
_extractor_instance = None


def get_extractor() -> FieldExtractor:
    """Get or create the singleton field extractor instance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = FieldExtractor()
    return _extractor_instance
