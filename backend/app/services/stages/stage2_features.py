"""Stage 2: Feature Vector Assembly Service
Assembles extracted fields into a unified BorrowerFeatureVector.
Handles priority merging (extraction vs manual) and calculates completeness.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, ExtractedField, BorrowerFeature
from app.schemas.shared import BorrowerFeatureVector, ExtractedFieldItem
from app.core.enums import EntityType

logger = logging.getLogger(__name__)


# Field mapping: ExtractedField.field_name -> BorrowerFeatureVector attribute
FIELD_MAPPING = {
    # Identity
    "full_name": "full_name",
    "pan_number": "pan_number",
    "aadhaar_number": "aadhaar_number",
    "dob": "dob",

    # Business
    "entity_type": "entity_type",
    "business_vintage_years": "business_vintage_years",
    "gstin": "gstin",
    "industry_type": "industry_type",
    "pincode": "pincode",

    # Financial
    "annual_turnover": "annual_turnover",
    "avg_monthly_balance": "avg_monthly_balance",
    "monthly_credit_avg": "monthly_credit_avg",
    "monthly_turnover": "monthly_turnover",
    "emi_outflow_monthly": "emi_outflow_monthly",
    "bounce_count_12m": "bounce_count_12m",
    "cash_deposit_ratio": "cash_deposit_ratio",
    "itr_total_income": "itr_total_income",

    # Credit
    "cibil_score": "cibil_score",
    "active_loan_count": "active_loan_count",
    "overdue_count": "overdue_count",
    "enquiry_count_6m": "enquiry_count_6m",
}

# Total number of fields in BorrowerFeatureVector (excluding meta fields)
TOTAL_FEATURE_FIELDS = len(FIELD_MAPPING)


class FeatureAssembler:
    """Assembles borrower feature vector from extracted fields and manual data."""

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize the feature assembler.

        Args:
            confidence_threshold: Minimum confidence for extracted values to override manual
        """
        self.confidence_threshold = confidence_threshold

    async def assemble_features(
        self,
        db: AsyncSession,
        case_id: str,
        extracted_fields: List[ExtractedFieldItem]
    ) -> BorrowerFeatureVector:
        """
        Assemble borrower feature vector from extracted fields and manual overrides.

        Priority logic:
        - If extraction confidence >= threshold: use extracted value
        - Else: use manual value from Case table if available
        - Else: use extracted value regardless of confidence (better than nothing)

        Args:
            db: Database session
            case_id: Case ID (UUID or case_id string)
            extracted_fields: List of extracted field items

        Returns:
            Assembled BorrowerFeatureVector with completeness score
        """
        # Fetch the case with manual overrides
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            logger.error(f"Case {case_id} not found")
            raise ValueError(f"Case {case_id} not found")

        # Initialize feature data
        feature_data = {}

        # Group extracted fields by field_name (take first match)
        extracted_by_name: Dict[str, ExtractedFieldItem] = {}
        for field in extracted_fields:
            if field.field_name not in extracted_by_name:
                extracted_by_name[field.field_name] = field

        # Manual overrides from Case table
        manual_overrides = {
            "full_name": case.borrower_name,
            "entity_type": case.entity_type,
            "business_vintage_years": case.business_vintage_years,
            "gstin": case.gstin,
            "cibil_score": case.cibil_score_manual,
            "industry_type": case.industry_type,
            "pincode": case.pincode,
        }

        if isinstance(case.gst_data, dict):
            gst_payload = case.gst_data
            gst_name = (
                gst_payload.get("borrower_name")
                or gst_payload.get("tradename")
                or gst_payload.get("trade_name")
                or gst_payload.get("name")
            )
            if gst_name and not manual_overrides.get("full_name"):
                manual_overrides["full_name"] = gst_name
            if gst_payload.get("entity_type") and not manual_overrides.get("entity_type"):
                manual_overrides["entity_type"] = gst_payload.get("entity_type")
            if gst_payload.get("business_vintage_years") is not None and manual_overrides.get("business_vintage_years") is None:
                manual_overrides["business_vintage_years"] = gst_payload.get("business_vintage_years")
            if gst_payload.get("pincode") and not manual_overrides.get("pincode"):
                manual_overrides["pincode"] = str(gst_payload.get("pincode"))
            gst_industry = (
                gst_payload.get("industry_type")
                or gst_payload.get("business_type")
                or gst_payload.get("nature_of_business")
                or gst_payload.get("natureOfBusiness")
            )
            if gst_industry and not manual_overrides.get("industry_type"):
                manual_overrides["industry_type"] = gst_industry

        # Process each field in the mapping
        for field_name, vector_attr in FIELD_MAPPING.items():
            extracted = extracted_by_name.get(field_name)
            manual = manual_overrides.get(field_name)

            # Apply priority logic
            final_value = self._resolve_field_value(
                field_name=field_name,
                extracted=extracted,
                manual=manual
            )

            # Convert to appropriate type
            final_value = self._convert_field_type(vector_attr, final_value)

            if final_value is not None:
                feature_data[vector_attr] = final_value

        # TASK 2: Set monthly_turnover = monthly_credit_avg (average of monthly credits)
        if "monthly_credit_avg" in feature_data and feature_data["monthly_credit_avg"] is not None:
            feature_data["monthly_turnover"] = feature_data["monthly_credit_avg"]
            logger.info(
                f"Set monthly_turnover = {feature_data['monthly_turnover']} "
                f"(from monthly_credit_avg)"
            )

        # Derive annual turnover in Lakhs from monthly bank credits when explicit turnover is missing.
        if (
            feature_data.get("annual_turnover") is None
            and feature_data.get("monthly_turnover") is not None
            and feature_data["monthly_turnover"] > 0
        ):
            annual_turnover_lakhs = round((feature_data["monthly_turnover"] * 12) / 100000, 2)
            feature_data["annual_turnover"] = annual_turnover_lakhs
            logger.info(
                "Derived annual_turnover=%sL from monthly_turnover=%s",
                annual_turnover_lakhs,
                feature_data["monthly_turnover"],
            )

        # Calculate feature completeness
        filled_count = sum(1 for v in feature_data.values() if v is not None)
        completeness = (filled_count / TOTAL_FEATURE_FIELDS) * 100

        # Create feature vector
        feature_vector = BorrowerFeatureVector(
            **feature_data,
            feature_completeness=round(completeness, 2)
        )

        return feature_vector

    def _resolve_field_value(
        self,
        field_name: str,
        extracted: Optional[ExtractedFieldItem],
        manual: Optional[Any]
    ) -> Optional[str]:
        """
        Resolve the final field value based on priority logic.

        Priority:
        1. Extracted value with confidence >= threshold
        2. Manual override (if available)
        3. Extracted value with any confidence (better than nothing)
        4. None

        Args:
            field_name: Name of the field
            extracted: Extracted field item (if available)
            manual: Manual override value (if available)

        Returns:
            Final field value as string (will be converted to proper type later)
        """
        # Case 1: High-confidence extraction
        if extracted and extracted.confidence >= self.confidence_threshold:
            logger.debug(
                f"Field {field_name}: Using extracted value "
                f"(confidence={extracted.confidence:.2f})"
            )
            return extracted.field_value

        # Case 2: Manual override available
        if manual is not None:
            logger.debug(f"Field {field_name}: Using manual override")
            return str(manual)

        # Case 3: Low-confidence extraction (better than nothing)
        if extracted:
            logger.debug(
                f"Field {field_name}: Using low-confidence extraction "
                f"(confidence={extracted.confidence:.2f})"
            )
            return extracted.field_value

        # Case 4: No data available
        return None

    def _convert_field_type(self, field_name: str, value: Optional[str]) -> Optional[Any]:
        """
        Convert field value to appropriate Python type based on BorrowerFeatureVector schema.

        Args:
            field_name: Attribute name in BorrowerFeatureVector
            value: String value to convert

        Returns:
            Converted value with appropriate type
        """
        if value is None:
            return None

        # String fields
        string_fields = [
            "full_name", "pan_number", "aadhaar_number", "gstin",
            "industry_type", "pincode"
        ]
        if field_name in string_fields:
            return str(value).strip()

        # Date fields
        if field_name == "dob":
            try:
                # Parse date in dd/mm/yyyy format
                date_str = value.replace('-', '/')
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                return dt.date()
            except ValueError:
                logger.warning(f"Could not parse date: {value}")
                return None

        # Float fields
        float_fields = [
            "annual_turnover", "avg_monthly_balance", "monthly_credit_avg",
            "monthly_turnover", "emi_outflow_monthly", "cash_deposit_ratio", "itr_total_income",
            "business_vintage_years"
        ]
        if field_name in float_fields:
            try:
                # Remove commas and convert to float
                clean_value = str(value).replace(',', '').strip()
                return float(clean_value)
            except ValueError:
                logger.warning(f"Could not convert to float: {value}")
                return None

        # Integer fields
        int_fields = [
            "cibil_score", "active_loan_count", "overdue_count",
            "enquiry_count_6m", "bounce_count_12m"
        ]
        if field_name in int_fields:
            try:
                clean_value = str(value).replace(',', '').strip()
                return int(float(clean_value))  # Handle "123.0" -> 123
            except ValueError:
                logger.warning(f"Could not convert to int: {value}")
                return None

        # Enum fields
        if field_name == "entity_type":
            try:
                return EntityType(value.lower())
            except ValueError:
                logger.warning(f"Invalid entity type: {value}")
                return None

        # Default: return as string
        return str(value).strip()

    async def save_feature_vector(
        self,
        db: AsyncSession,
        case_id: str,
        feature_vector: BorrowerFeatureVector
    ) -> BorrowerFeature:
        """
        Save or update the borrower feature vector in the database.

        Args:
            db: Database session
            case_id: Case ID (UUID or case_id string)
            feature_vector: Assembled feature vector

        Returns:
            Saved BorrowerFeature database model
        """
        # Get case UUID
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Check if feature record already exists
        query = select(BorrowerFeature).where(BorrowerFeature.case_id == case.id)
        result = await db.execute(query)
        existing = result.scalar_one_or_none()

        # Convert feature vector to dict
        feature_dict = feature_vector.model_dump(exclude_none=False)

        # Convert date to datetime for database storage
        if feature_dict.get("dob") and isinstance(feature_dict["dob"], date):
            feature_dict["dob"] = datetime.combine(feature_dict["dob"], datetime.min.time())

        if existing:
            # Update existing record
            for key, value in feature_dict.items():
                setattr(existing, key, value)
            if not existing.organization_id:
                existing.organization_id = case.organization_id
            borrower_feature = existing
            logger.info(f"Updated feature vector for case {case_id}")
        else:
            # Create new record
            borrower_feature = BorrowerFeature(
                case_id=case.id,
                organization_id=case.organization_id,
                **feature_dict
            )
            db.add(borrower_feature)
            logger.info(f"Created feature vector for case {case_id}")

        await db.commit()
        await db.refresh(borrower_feature)

        return borrower_feature

    async def save_extracted_fields(
        self,
        db: AsyncSession,
        case_id: str,
        document_id: Optional[str],
        fields: List[ExtractedFieldItem]
    ) -> List[ExtractedField]:
        """
        Save extracted fields to the database.

        Args:
            db: Database session
            case_id: Case ID (UUID or case_id string)
            document_id: Document UUID (optional)
            fields: List of extracted field items

        Returns:
            List of saved ExtractedField database models
        """
        # Get case UUID
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        saved_fields = []
        for field_item in fields:
            extracted_field = ExtractedField(
                case_id=case.id,
                document_id=document_id,
                organization_id=case.organization_id,
                field_name=field_item.field_name,
                field_value=field_item.field_value,
                confidence=field_item.confidence,
                source=field_item.source
            )
            db.add(extracted_field)
            saved_fields.append(extracted_field)

        # Flush to assign DB-generated values; caller controls transaction commit.
        await db.flush()

        logger.info(f"Saved {len(saved_fields)} extracted fields for case {case_id}")
        return saved_fields

    async def get_extracted_fields(
        self,
        db: AsyncSession,
        case_id: str
    ) -> List[ExtractedFieldItem]:
        """
        Get all extracted fields for a case.

        Args:
            db: Database session
            case_id: Case ID (UUID or case_id string)

        Returns:
            List of extracted field items
        """
        # Get case UUID
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Fetch all extracted fields
        query = select(ExtractedField).where(ExtractedField.case_id == case.id)
        result = await db.execute(query)
        fields = result.scalars().all()

        # Convert to schema
        return [
            ExtractedFieldItem(
                field_name=field.field_name,
                field_value=field.field_value,
                confidence=field.confidence,
                source=field.source
            )
            for field in fields
        ]

    async def get_feature_vector(
        self,
        db: AsyncSession,
        case_id: str
    ) -> Optional[BorrowerFeatureVector]:
        """
        Get the assembled feature vector for a case.

        Args:
            db: Database session
            case_id: Case ID (UUID or case_id string)

        Returns:
            BorrowerFeatureVector or None if not found
        """
        # Get case UUID
        query = select(Case).where(Case.case_id == case_id)
        result = await db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Fetch feature record
        query = select(BorrowerFeature).where(BorrowerFeature.case_id == case.id)
        result = await db.execute(query)
        feature = result.scalar_one_or_none()

        if not feature:
            return None

        # Convert to schema
        feature_dict = {
            "full_name": feature.full_name,
            "pan_number": feature.pan_number,
            "aadhaar_number": feature.aadhaar_number,
            "dob": feature.dob if feature.dob else None,  # Already a date object, no need for .date()
            "entity_type": EntityType(feature.entity_type) if feature.entity_type else None,
            "business_vintage_years": feature.business_vintage_years,
            "gstin": feature.gstin,
            "industry_type": feature.industry_type,
            "pincode": feature.pincode,
            "annual_turnover": feature.annual_turnover,
            "avg_monthly_balance": feature.avg_monthly_balance,
            "monthly_credit_avg": feature.monthly_credit_avg,
            "monthly_turnover": feature.monthly_turnover,
            "emi_outflow_monthly": feature.emi_outflow_monthly,
            "bounce_count_12m": feature.bounce_count_12m,
            "cash_deposit_ratio": feature.cash_deposit_ratio,
            "itr_total_income": feature.itr_total_income,
            "cibil_score": feature.cibil_score,
            "active_loan_count": feature.active_loan_count,
            "overdue_count": feature.overdue_count,
            "enquiry_count_6m": feature.enquiry_count_6m,
            "feature_completeness": feature.feature_completeness,
        }

        return BorrowerFeatureVector(**feature_dict)


# Singleton instance
_assembler_instance = None


def get_assembler() -> FeatureAssembler:
    """Get or create the singleton feature assembler instance."""
    global _assembler_instance
    if _assembler_instance is None:
        _assembler_instance = FeatureAssembler()
    return _assembler_instance
