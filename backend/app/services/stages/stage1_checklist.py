"""Stage 1: Document Checklist Engine - Validates document completeness per program type."""
import logging
from typing import List, Dict, Set, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.case import Case, Document
from app.schemas.shared import DocumentChecklist, ManualFieldPrompt
from app.core.enums import ProgramType, DocumentType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DOCUMENT REQUIREMENTS PER PROGRAM TYPE
# ═══════════════════════════════════════════════════════════════

PROGRAM_REQUIREMENTS: Dict[ProgramType, Dict[str, Set[DocumentType]]] = {
    ProgramType.BANKING: {
        "required": {
            DocumentType.BANK_STATEMENT,      # 12 months - CRITICAL
            DocumentType.AADHAAR,
            DocumentType.GST_CERTIFICATE,
            DocumentType.CIBIL_REPORT,
        },
        "required_any_of": {                   # Must have at least one
            DocumentType.PAN_PERSONAL,
            DocumentType.PAN_BUSINESS,
        },
        "optional": {
            DocumentType.UDYAM_SHOP_LICENSE,
            DocumentType.PROPERTY_DOCUMENTS,
            DocumentType.GST_RETURNS,
        }
    },
    ProgramType.INCOME: {
        "required": {
            DocumentType.ITR,                  # 2-3 years
            DocumentType.FINANCIAL_STATEMENTS,
            DocumentType.AADHAAR,
            DocumentType.CIBIL_REPORT,
        },
        "required_any_of": {
            DocumentType.PAN_PERSONAL,
            DocumentType.PAN_BUSINESS,
        },
        "optional": {
            DocumentType.UDYAM_SHOP_LICENSE,
            DocumentType.PROPERTY_DOCUMENTS,
            DocumentType.GST_CERTIFICATE,
            DocumentType.GST_RETURNS,
        }
    },
    ProgramType.HYBRID: {
        "required": {
            DocumentType.BANK_STATEMENT,
            DocumentType.ITR,
            DocumentType.GST_CERTIFICATE,
            DocumentType.CIBIL_REPORT,
            DocumentType.AADHAAR,
        },
        "required_any_of": {
            DocumentType.PAN_PERSONAL,
            DocumentType.PAN_BUSINESS,
        },
        "optional": {
            DocumentType.UDYAM_SHOP_LICENSE,
            DocumentType.PROPERTY_DOCUMENTS,
            DocumentType.GST_RETURNS,
            DocumentType.FINANCIAL_STATEMENTS,
        }
    }
}


# ═══════════════════════════════════════════════════════════════
# PROGRESSIVE DATA CAPTURE MAPPING
# ═══════════════════════════════════════════════════════════════

MANUAL_FIELD_MAPPINGS = {
    DocumentType.CIBIL_REPORT: {
        "field_name": "cibil_score_manual",
        "label": "CIBIL Score",
        "field_type": "number",
        "reason": "CIBIL report not uploaded"
    },
    DocumentType.GST_CERTIFICATE: [
        {
            "field_name": "business_vintage_years",
            "label": "Business Vintage (years)",
            "field_type": "number",
            "reason": "GST certificate not uploaded"
        },
        {
            "field_name": "entity_type",
            "label": "Entity Type",
            "field_type": "select",
            "reason": "GST certificate not uploaded"
        }
    ],
    DocumentType.GST_RETURNS: {
        "field_name": "monthly_turnover_manual",
        "label": "Approximate Monthly Turnover (₹)",
        "field_type": "number",
        "reason": "GST returns not uploaded"
    }
}


class ChecklistEngine:
    """
    Document Checklist Engine for Stage 1.

    Responsibilities:
    1. Validate document completeness per program type
    2. Calculate completeness score (0-100)
    3. Identify missing documents
    4. Generate progressive data capture prompts
    5. Update case completeness score
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_checklist(
        self,
        case_id: str,
        user_id: UUID
    ) -> DocumentChecklist:
        """
        Generate document checklist for a case.

        Args:
            case_id: Case ID (format: CASE-YYYYMMDD-XXXX)
            user_id: User ID for verification

        Returns:
            DocumentChecklist with available/missing docs and completeness score

        Raises:
            ValueError: If case not found or program type not set
        """
        # Get case with documents
        case = await self._get_case_with_documents(case_id, user_id)

        # Validate program type is set
        if not case.program_type:
            raise ValueError("Program type must be set before generating checklist")

        program_type = ProgramType(case.program_type)

        # Get classified document types (excluding UNKNOWN and None)
        classified_docs = [
            DocumentType(doc.doc_type)
            for doc in case.documents
            if doc.doc_type and doc.doc_type != DocumentType.UNKNOWN.value
        ]

        # Get unreadable/unclassified documents
        unreadable = [
            doc.original_filename
            for doc in case.documents
            if not doc.doc_type or doc.doc_type == DocumentType.UNKNOWN.value
        ]

        # Get requirements for program type
        requirements = PROGRAM_REQUIREMENTS[program_type]
        required_docs = requirements["required"]
        required_any_of = requirements.get("required_any_of", set())
        optional_docs = requirements.get("optional", set())

        # Calculate available and missing
        available_set = set(classified_docs)

        # ── Manual overrides count as virtual documents ──
        # If user manually entered CIBIL score, treat CIBIL_REPORT as covered
        if case.cibil_score_manual and case.cibil_score_manual > 0:
            available_set.add(DocumentType.CIBIL_REPORT)
        # If user manually entered business vintage, treat GST_CERTIFICATE as covered
        if case.business_vintage_years and case.business_vintage_years > 0:
            available_set.add(DocumentType.GST_CERTIFICATE)
        # If user manually entered monthly turnover, treat GST_RETURNS as covered
        if case.monthly_turnover_manual and case.monthly_turnover_manual > 0:
            available_set.add(DocumentType.GST_RETURNS)

        available = list(available_set)

        # Check required documents
        missing = []
        for doc_type in required_docs:
            if doc_type not in available_set:
                missing.append(doc_type)

        # Check "any of" requirements
        if required_any_of:
            if not any(doc_type in available_set for doc_type in required_any_of):
                # Add all options as missing (user needs to upload at least one)
                missing.extend(list(required_any_of))

        # Identify optional documents present
        optional_present = [
            doc_type for doc_type in optional_docs
            if doc_type in available_set
        ]

        # Calculate completeness score
        completeness_score = self._calculate_completeness(
            available_set,
            required_docs,
            required_any_of
        )

        return DocumentChecklist(
            program_type=program_type,
            available=available,
            missing=missing,
            unreadable=unreadable,
            optional_present=optional_present,
            completeness_score=completeness_score
        )

    def _calculate_completeness(
        self,
        available: Set[DocumentType],
        required: Set[DocumentType],
        required_any_of: Set[DocumentType]
    ) -> float:
        """
        Calculate completeness score (0-100).

        Logic:
        - Each required doc = 1 point
        - Any-of requirement = 1 point (satisfied if ANY doc from set is present)
        - Score = (points earned / total points) × 100

        Args:
            available: Set of available document types
            required: Set of required document types
            required_any_of: Set of "any of" document types

        Returns:
            Completeness score (0-100)
        """
        total_points = len(required)
        earned_points = 0

        # Count required docs
        for doc_type in required:
            if doc_type in available:
                earned_points += 1

        # Check "any of" requirement (counts as 1 point)
        if required_any_of:
            total_points += 1
            if any(doc_type in available for doc_type in required_any_of):
                earned_points += 1

        if total_points == 0:
            return 0.0

        return round((earned_points / total_points) * 100, 2)

    async def get_missing_manual_prompts(
        self,
        case_id: str,
        user_id: UUID
    ) -> List[ManualFieldPrompt]:
        """
        Get list of manual data entry prompts for missing documents.

        Args:
            case_id: Case ID
            user_id: User ID for verification

        Returns:
            List of ManualFieldPrompt for fields that can be manually entered
        """
        # Get case
        case = await self._get_case_with_documents(case_id, user_id)

        if not case.program_type:
            return []

        # Generate checklist to identify missing docs
        checklist = await self.generate_checklist(case_id, user_id)

        prompts = []

        # Generate prompts for missing documents
        for doc_type in checklist.missing:
            if doc_type in MANUAL_FIELD_MAPPINGS:
                mapping = MANUAL_FIELD_MAPPINGS[doc_type]

                # Handle single mapping
                if isinstance(mapping, dict):
                    prompts.append(self._create_prompt(mapping, case))
                # Handle multiple mappings (e.g., GST certificate)
                elif isinstance(mapping, list):
                    for field_mapping in mapping:
                        prompts.append(self._create_prompt(field_mapping, case))

        return prompts

    def _create_prompt(
        self,
        mapping: dict,
        case: Case
    ) -> ManualFieldPrompt:
        """Create a ManualFieldPrompt from mapping and case data."""
        field_name = mapping["field_name"]
        current_value = getattr(case, field_name, None)

        return ManualFieldPrompt(
            field_name=field_name,
            label=mapping["label"],
            reason=mapping["reason"],
            field_type=mapping["field_type"],
            current_value=current_value
        )

    async def update_completeness(
        self,
        case_id: str,
        user_id: UUID
    ) -> float:
        """
        Update and return the completeness score for a case.

        This should be called whenever:
        - New documents are uploaded
        - Documents are classified
        - Manual data is entered
        - Program type is changed

        Args:
            case_id: Case ID
            user_id: User ID for verification

        Returns:
            Updated completeness score (0-100)
        """
        try:
            # Get case
            case = await self._get_case_with_documents(case_id, user_id)

            # If program type not set, score is 0
            if not case.program_type:
                case.completeness_score = 0.0
                await self.db.commit()
                return 0.0

            # Generate checklist
            checklist = await self.generate_checklist(case_id, user_id)

            # Update case completeness score
            case.completeness_score = checklist.completeness_score
            await self.db.commit()

            # Log warnings based on score
            if checklist.completeness_score < 30:
                logger.warning(
                    f"CRITICAL: Case {case_id} completeness is {checklist.completeness_score}% - "
                    f"missing critical documents"
                )
            elif checklist.completeness_score < 60:
                logger.warning(
                    f"WARNING: Case {case_id} completeness is {checklist.completeness_score}% - "
                    f"missing important documents"
                )

            return checklist.completeness_score

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update completeness for case {case_id}: {e}")
            raise

    async def _get_case_with_documents(
        self,
        case_id: str,
        user_id: UUID
    ) -> Case:
        """Get case with documents, verifying ownership."""
        query = select(Case).where(
            Case.case_id == case_id,
            Case.user_id == user_id
        ).options(selectinload(Case.documents))

        result = await self.db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        return case
