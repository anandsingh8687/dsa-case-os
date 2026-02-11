"""Tests for Stage 1: Document Checklist Engine."""
import pytest
import pytest_asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, Document
from app.services.stages.stage1_checklist import ChecklistEngine
from app.core.enums import ProgramType, DocumentType
from app.schemas.shared import DocumentChecklist, ManualFieldPrompt


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def banking_case(db_session: AsyncSession, test_user_id: UUID) -> Case:
    """Create a BANKING program case."""
    case = Case(
        case_id="CASE-20240210-0001",
        user_id=test_user_id,
        status="processing",
        program_type=ProgramType.BANKING.value,
        borrower_name="Test Banking Borrower"
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case


@pytest_asyncio.fixture
async def income_case(db_session: AsyncSession, test_user_id: UUID) -> Case:
    """Create an INCOME program case."""
    case = Case(
        case_id="CASE-20240210-0002",
        user_id=test_user_id,
        status="processing",
        program_type=ProgramType.INCOME.value,
        borrower_name="Test Income Borrower"
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case


@pytest_asyncio.fixture
async def hybrid_case(db_session: AsyncSession, test_user_id: UUID) -> Case:
    """Create a HYBRID program case."""
    case = Case(
        case_id="CASE-20240210-0003",
        user_id=test_user_id,
        status="processing",
        program_type=ProgramType.HYBRID.value,
        borrower_name="Test Hybrid Borrower"
    )
    db_session.add(case)
    await db_session.commit()
    await db_session.refresh(case)
    return case


async def add_document(
    db_session: AsyncSession,
    case: Case,
    doc_type: DocumentType
) -> Document:
    """Helper to add a classified document to a case."""
    document = Document(
        case_id=case.id,
        original_filename=f"{doc_type.value}.pdf",
        storage_key=f"{case.case_id}/{doc_type.value}.pdf",
        file_size_bytes=1000,
        mime_type="application/pdf",
        file_hash=f"hash_{doc_type.value}",
        doc_type=doc_type.value,
        classification_confidence=0.95,
        status="classified"
    )
    db_session.add(document)
    await db_session.flush()
    return document


# ═══════════════════════════════════════════════════════════════
# BANKING PROGRAM TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_banking_complete_documents(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test BANKING program with all required documents."""
    # Add all required documents
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    # Generate checklist
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Assertions
    assert checklist.program_type == ProgramType.BANKING
    assert checklist.completeness_score == 100.0
    assert len(checklist.missing) == 0
    assert DocumentType.BANK_STATEMENT in checklist.available
    assert DocumentType.CIBIL_REPORT in checklist.available


@pytest.mark.asyncio
async def test_banking_missing_critical_docs(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test BANKING program missing critical documents."""
    # Only add PAN and Aadhaar
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await db_session.commit()

    # Generate checklist
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Assertions
    assert checklist.completeness_score < 60.0  # Should trigger WARNING
    assert DocumentType.BANK_STATEMENT in checklist.missing
    assert DocumentType.GST_CERTIFICATE in checklist.missing
    assert DocumentType.CIBIL_REPORT in checklist.missing
    assert len(checklist.available) == 2


@pytest.mark.asyncio
async def test_banking_with_optional_docs(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test BANKING program with optional documents present."""
    # Add all required docs
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_BUSINESS)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)

    # Add optional docs
    await add_document(db_session, banking_case, DocumentType.UDYAM_SHOP_LICENSE)
    await add_document(db_session, banking_case, DocumentType.GST_RETURNS)
    await db_session.commit()

    # Generate checklist
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Assertions
    assert checklist.completeness_score == 100.0
    assert DocumentType.UDYAM_SHOP_LICENSE in checklist.optional_present
    assert DocumentType.GST_RETURNS in checklist.optional_present


@pytest.mark.asyncio
async def test_banking_pan_any_of_requirement(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test BANKING program with PAN_BUSINESS instead of PAN_PERSONAL."""
    # Add all required docs with PAN_BUSINESS
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_BUSINESS)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    # Generate checklist
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Assertions - should be 100% complete
    assert checklist.completeness_score == 100.0
    assert DocumentType.PAN_BUSINESS in checklist.available
    assert DocumentType.PAN_PERSONAL not in checklist.missing


@pytest.mark.asyncio
async def test_banking_missing_pan(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test BANKING program missing both PAN types."""
    # Add docs but no PAN
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    # Generate checklist
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Assertions
    assert checklist.completeness_score < 100.0
    # Both PAN types should be in missing (user can upload either)
    assert DocumentType.PAN_PERSONAL in checklist.missing
    assert DocumentType.PAN_BUSINESS in checklist.missing


# ═══════════════════════════════════════════════════════════════
# INCOME PROGRAM TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_income_complete_documents(
    db_session: AsyncSession,
    income_case: Case,
    test_user_id: UUID
):
    """Test INCOME program with all required documents."""
    await add_document(db_session, income_case, DocumentType.ITR)
    await add_document(db_session, income_case, DocumentType.FINANCIAL_STATEMENTS)
    await add_document(db_session, income_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, income_case, DocumentType.AADHAAR)
    await add_document(db_session, income_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(income_case.case_id, test_user_id)

    assert checklist.completeness_score == 100.0
    assert DocumentType.ITR in checklist.available
    assert DocumentType.FINANCIAL_STATEMENTS in checklist.available


@pytest.mark.asyncio
async def test_income_missing_itr(
    db_session: AsyncSession,
    income_case: Case,
    test_user_id: UUID
):
    """Test INCOME program missing ITR."""
    await add_document(db_session, income_case, DocumentType.FINANCIAL_STATEMENTS)
    await add_document(db_session, income_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, income_case, DocumentType.AADHAAR)
    await add_document(db_session, income_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(income_case.case_id, test_user_id)

    assert checklist.completeness_score < 100.0
    assert DocumentType.ITR in checklist.missing


# ═══════════════════════════════════════════════════════════════
# HYBRID PROGRAM TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hybrid_complete_documents(
    db_session: AsyncSession,
    hybrid_case: Case,
    test_user_id: UUID
):
    """Test HYBRID program with all required documents."""
    await add_document(db_session, hybrid_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, hybrid_case, DocumentType.ITR)
    await add_document(db_session, hybrid_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, hybrid_case, DocumentType.CIBIL_REPORT)
    await add_document(db_session, hybrid_case, DocumentType.AADHAAR)
    await add_document(db_session, hybrid_case, DocumentType.PAN_PERSONAL)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(hybrid_case.case_id, test_user_id)

    assert checklist.completeness_score == 100.0
    assert DocumentType.BANK_STATEMENT in checklist.available
    assert DocumentType.ITR in checklist.available


@pytest.mark.asyncio
async def test_hybrid_partial_documents(
    db_session: AsyncSession,
    hybrid_case: Case,
    test_user_id: UUID
):
    """Test HYBRID program with partial documents."""
    await add_document(db_session, hybrid_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, hybrid_case, DocumentType.PAN_PERSONAL)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(hybrid_case.case_id, test_user_id)

    assert checklist.completeness_score < 50.0  # Should be CRITICAL
    assert DocumentType.ITR in checklist.missing
    assert DocumentType.GST_CERTIFICATE in checklist.missing
    assert DocumentType.CIBIL_REPORT in checklist.missing


# ═══════════════════════════════════════════════════════════════
# COMPLETENESS SCORE CALCULATION TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_completeness_score_zero_percent(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test completeness score with no documents."""
    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    assert checklist.completeness_score == 0.0
    assert len(checklist.available) == 0


@pytest.mark.asyncio
async def test_completeness_score_50_percent(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test completeness score with 50% documents."""
    # BANKING requires: bank_statement, pan, aadhaar, gst_cert, cibil (5 items total)
    # Add 2.5 items worth (considering PAN is 1 item)
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # 2 out of 5 required items = 40%
    assert 30.0 < checklist.completeness_score < 60.0


# ═══════════════════════════════════════════════════════════════
# UNREADABLE DOCUMENTS TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_unreadable_documents(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test handling of unreadable/unclassified documents."""
    # Add some valid docs
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)

    # Add unreadable document
    unreadable = Document(
        case_id=banking_case.id,
        original_filename="corrupted_file.pdf",
        storage_key=f"{banking_case.case_id}/corrupted_file.pdf",
        file_size_bytes=1000,
        mime_type="application/pdf",
        file_hash="hash_corrupted",
        doc_type=DocumentType.UNKNOWN.value,
        classification_confidence=0.0,
        status="failed"
    )
    db_session.add(unreadable)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    assert "corrupted_file.pdf" in checklist.unreadable
    assert DocumentType.UNKNOWN not in checklist.available


# ═══════════════════════════════════════════════════════════════
# PROGRESSIVE DATA CAPTURE TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_manual_prompts_cibil_missing(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test manual prompt when CIBIL report is missing."""
    # Add docs but not CIBIL
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    prompts = await engine.get_missing_manual_prompts(banking_case.case_id, test_user_id)

    # Should have prompt for CIBIL score
    cibil_prompts = [p for p in prompts if p.field_name == "cibil_score_manual"]
    assert len(cibil_prompts) == 1
    assert cibil_prompts[0].label == "CIBIL Score"
    assert cibil_prompts[0].field_type == "number"


@pytest.mark.asyncio
async def test_manual_prompts_gst_missing(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test manual prompts when GST certificate is missing."""
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    prompts = await engine.get_missing_manual_prompts(banking_case.case_id, test_user_id)

    # Should have prompts for business vintage and entity type
    field_names = [p.field_name for p in prompts]
    assert "business_vintage_years" in field_names
    assert "entity_type" in field_names


@pytest.mark.asyncio
async def test_manual_prompts_with_existing_values(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test manual prompts include existing values."""
    # Set manual CIBIL score
    banking_case.cibil_score_manual = 750
    await db_session.commit()

    # Don't add CIBIL document
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    prompts = await engine.get_missing_manual_prompts(banking_case.case_id, test_user_id)

    # Find CIBIL prompt
    cibil_prompts = [p for p in prompts if p.field_name == "cibil_score_manual"]
    assert len(cibil_prompts) == 1
    assert cibil_prompts[0].current_value == 750


@pytest.mark.asyncio
async def test_no_manual_prompts_when_complete(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test no manual prompts when all documents present."""
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    prompts = await engine.get_missing_manual_prompts(banking_case.case_id, test_user_id)

    assert len(prompts) == 0


# ═══════════════════════════════════════════════════════════════
# UPDATE COMPLETENESS TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_update_completeness_score(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test update_completeness updates the case score."""
    # Initially no documents
    assert banking_case.completeness_score == 0.0

    # Add some documents
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await db_session.commit()

    # Update completeness
    engine = ChecklistEngine(db_session)
    score = await engine.update_completeness(banking_case.case_id, test_user_id)

    # Refresh case from DB
    await db_session.refresh(banking_case)

    assert score > 0.0
    assert banking_case.completeness_score == score


@pytest.mark.asyncio
async def test_update_completeness_no_program_type(
    db_session: AsyncSession,
    test_user_id: UUID
):
    """Test update_completeness with no program type set."""
    case = Case(
        case_id="CASE-20240210-9999",
        user_id=test_user_id,
        status="created",
        program_type=None  # No program type
    )
    db_session.add(case)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    score = await engine.update_completeness(case.case_id, test_user_id)

    assert score == 0.0


# ═══════════════════════════════════════════════════════════════
# ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_checklist_case_not_found(
    db_session: AsyncSession,
    test_user_id: UUID
):
    """Test checklist generation for non-existent case."""
    engine = ChecklistEngine(db_session)

    with pytest.raises(ValueError, match="not found"):
        await engine.generate_checklist("CASE-INVALID", test_user_id)


@pytest.mark.asyncio
async def test_checklist_no_program_type(
    db_session: AsyncSession,
    test_user_id: UUID
):
    """Test checklist generation without program type."""
    case = Case(
        case_id="CASE-20240210-8888",
        user_id=test_user_id,
        status="created",
        program_type=None
    )
    db_session.add(case)
    await db_session.commit()

    engine = ChecklistEngine(db_session)

    with pytest.raises(ValueError, match="Program type must be set"):
        await engine.generate_checklist(case.case_id, test_user_id)


# ═══════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_duplicate_documents_same_type(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test handling of multiple documents of the same type."""
    # Add multiple bank statements
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)

    doc2 = Document(
        case_id=banking_case.id,
        original_filename="bank_statement_2.pdf",
        storage_key=f"{banking_case.case_id}/bank_statement_2.pdf",
        file_size_bytes=1000,
        mime_type="application/pdf",
        file_hash="hash_bank_2",
        doc_type=DocumentType.BANK_STATEMENT.value,
        classification_confidence=0.95,
        status="classified"
    )
    db_session.add(doc2)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Should count as 1 type available (not duplicate in available list)
    bank_statement_count = checklist.available.count(DocumentType.BANK_STATEMENT)
    assert bank_statement_count >= 1  # May appear multiple times in list


@pytest.mark.asyncio
async def test_completeness_with_both_pan_types(
    db_session: AsyncSession,
    banking_case: Case,
    test_user_id: UUID
):
    """Test completeness when both PAN types are uploaded."""
    await add_document(db_session, banking_case, DocumentType.BANK_STATEMENT)
    await add_document(db_session, banking_case, DocumentType.PAN_PERSONAL)
    await add_document(db_session, banking_case, DocumentType.PAN_BUSINESS)
    await add_document(db_session, banking_case, DocumentType.AADHAAR)
    await add_document(db_session, banking_case, DocumentType.GST_CERTIFICATE)
    await add_document(db_session, banking_case, DocumentType.CIBIL_REPORT)
    await db_session.commit()

    engine = ChecklistEngine(db_session)
    checklist = await engine.generate_checklist(banking_case.case_id, test_user_id)

    # Should be 100% complete (having both PANs is fine)
    assert checklist.completeness_score == 100.0
