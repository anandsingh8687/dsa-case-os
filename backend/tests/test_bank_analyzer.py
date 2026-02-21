"""Tests for Bank Statement Analyzer - Stage 2 metrics computation."""
import pytest
from datetime import date, timedelta
from typing import List, Dict, Any

from app.services.stages.stage2_bank_analyzer import BankStatementAnalyzer
from app.schemas.shared import BankAnalysisResult


# ============================================================================
# Test Fixtures
# ============================================================================

def create_sample_transaction(
    txn_date: date,
    narration: str,
    withdrawal_amt: float = 0.0,
    deposit_amt: float = 0.0,
    closing_balance: float = 50000.0,
    cheque_ref_no: str = ""
) -> Dict[str, Any]:
    """Create a sample transaction for testing."""
    return {
        'transactionDate': txn_date,
        'valueDate': txn_date,
        'narration': narration,
        'chequeRefNo': cheque_ref_no,
        'withdrawalAmt': withdrawal_amt,
        'depositAmt': deposit_amt,
        'closingBalance': closing_balance,
    }


@pytest.fixture
def analyzer():
    """Create a BankStatementAnalyzer instance."""
    return BankStatementAnalyzer()


@pytest.fixture
def sample_transactions_3_months():
    """Create sample transactions spanning 3 months."""
    transactions = []
    base_date = date(2024, 1, 1)

    # Month 1: January
    transactions.append(create_sample_transaction(
        txn_date=base_date,
        narration="SALARY CREDIT",
        deposit_amt=75000.0,
        closing_balance=125000.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=base_date + timedelta(days=5),
        narration="HDFC LOAN EMI",
        withdrawal_amt=15000.0,
        closing_balance=110000.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=base_date + timedelta(days=10),
        narration="ATM WITHDRAWAL",
        withdrawal_amt=5000.0,
        closing_balance=105000.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=base_date + timedelta(days=15),
        narration="CASH DEPOSIT",
        deposit_amt=10000.0,
        closing_balance=115000.0
    ))

    # Month 2: February
    feb_date = date(2024, 2, 1)
    transactions.append(create_sample_transaction(
        txn_date=feb_date,
        narration="SALARY CREDIT",
        deposit_amt=75000.0,
        closing_balance=190000.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=feb_date + timedelta(days=5),
        narration="HDFC LOAN EMI",
        withdrawal_amt=15000.0,
        closing_balance=175000.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=feb_date + timedelta(days=12),
        narration="ECS RETURN INSUFFICIENT FUNDS",
        withdrawal_amt=50.0,
        closing_balance=174950.0
    ))

    # Month 3: March
    mar_date = date(2024, 3, 1)
    transactions.append(create_sample_transaction(
        txn_date=mar_date,
        narration="SALARY CREDIT",
        deposit_amt=75000.0,
        closing_balance=249950.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=mar_date + timedelta(days=5),
        narration="HDFC LOAN EMI",
        withdrawal_amt=15000.0,
        closing_balance=234950.0
    ))
    transactions.append(create_sample_transaction(
        txn_date=mar_date + timedelta(days=20),
        narration="CASH DEP BY CASH",
        deposit_amt=20000.0,
        closing_balance=254950.0
    ))

    return transactions


# ============================================================================
# Basic Functionality Tests
# ============================================================================

@pytest.mark.asyncio
async def test_analyze_empty_transactions(analyzer):
    """Test analyzer with empty transactions list."""
    result = await analyzer.analyze_from_transactions(
        transactions=[],
        bank_detected="HDFC",
        account_number="12345678901234"
    )

    assert isinstance(result, BankAnalysisResult)
    assert result.transaction_count == 0
    assert result.confidence == 0.0
    assert result.bank_detected == "HDFC"
    assert result.account_number == "12345678901234"


@pytest.mark.asyncio
async def test_analyze_basic_metrics(analyzer, sample_transactions_3_months):
    """Test basic metric computation with 3 months of data."""
    result = await analyzer.analyze_from_transactions(
        transactions=sample_transactions_3_months,
        bank_detected="HDFC",
        account_number="12345678901234"
    )

    assert result.transaction_count == 10
    assert result.statement_period_months == 3
    assert result.bank_detected == "HDFC"

    # Check that all main metrics are computed
    assert result.avg_monthly_balance is not None
    assert result.monthly_credit_avg is not None
    assert result.monthly_debit_avg is not None
    assert result.emi_outflow_monthly is not None
    assert result.cash_deposit_ratio is not None
    assert result.peak_balance is not None
    assert result.min_balance is not None
    assert result.confidence > 0


# ============================================================================
# Average Monthly Balance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_avg_monthly_balance_calculation(analyzer):
    """Test average monthly balance calculation."""
    transactions = [
        # January - ending balance 100000
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="DEPOSIT",
            deposit_amt=50000.0,
            closing_balance=100000.0
        ),
        # February - ending balance 120000
        create_sample_transaction(
            txn_date=date(2024, 2, 15),
            narration="DEPOSIT",
            deposit_amt=20000.0,
            closing_balance=120000.0
        ),
        # March - ending balance 110000
        create_sample_transaction(
            txn_date=date(2024, 3, 15),
            narration="WITHDRAWAL",
            withdrawal_amt=10000.0,
            closing_balance=110000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Average = (100000 + 120000 + 110000) / 3 = 110000
    assert result.avg_monthly_balance == 110000.0


@pytest.mark.asyncio
async def test_avg_monthly_balance_single_month(analyzer):
    """Test average monthly balance with single month data."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="DEPOSIT",
            deposit_amt=50000.0,
            closing_balance=75000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="WITHDRAWAL",
            withdrawal_amt=10000.0,
            closing_balance=65000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Only one month, so average = 65000 (last balance of the month)
    assert result.avg_monthly_balance == 65000.0


# ============================================================================
# Monthly Credit/Debit Average Tests
# ============================================================================

@pytest.mark.asyncio
async def test_monthly_credit_avg(analyzer):
    """Test average monthly credits calculation."""
    transactions = [
        # January: 50000 + 30000 = 80000
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY",
            deposit_amt=50000.0,
            closing_balance=100000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="BONUS",
            deposit_amt=30000.0,
            closing_balance=130000.0
        ),
        # February: 50000
        create_sample_transaction(
            txn_date=date(2024, 2, 5),
            narration="SALARY",
            deposit_amt=50000.0,
            closing_balance=180000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Average = (80000 + 50000) / 2 = 65000
    assert result.monthly_credit_avg == 65000.0


@pytest.mark.asyncio
async def test_monthly_debit_avg(analyzer):
    """Test average monthly debits calculation."""
    transactions = [
        # January: 10000 + 5000 = 15000
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="RENT",
            withdrawal_amt=10000.0,
            closing_balance=90000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="UTILITIES",
            withdrawal_amt=5000.0,
            closing_balance=85000.0
        ),
        # February: 20000
        create_sample_transaction(
            txn_date=date(2024, 2, 5),
            narration="EMI",
            withdrawal_amt=20000.0,
            closing_balance=65000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Average = (15000 + 20000) / 2 = 17500
    assert result.monthly_debit_avg == 17500.0


# ============================================================================
# EMI Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_emi_detection_basic(analyzer):
    """Test EMI detection with standard keywords."""
    transactions = [
        # Month 1
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="HDFC HOME LOAN EMI",
            withdrawal_amt=25000.0,
            closing_balance=75000.0
        ),
        # Month 2
        create_sample_transaction(
            txn_date=date(2024, 2, 5),
            narration="HDFC HOME LOAN EMI",
            withdrawal_amt=25000.0,
            closing_balance=50000.0
        ),
        # Non-EMI transaction
        create_sample_transaction(
            txn_date=date(2024, 2, 15),
            narration="SHOPPING",
            withdrawal_amt=5000.0,
            closing_balance=45000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Average EMI = (25000 + 25000) / 2 = 25000
    assert result.emi_outflow_monthly == 25000.0


@pytest.mark.asyncio
async def test_emi_detection_various_keywords(analyzer):
    """Test EMI detection with various keyword patterns."""
    emi_keywords_tests = [
        "NACH DEBIT FOR ICICI LOAN",
        "ECS SI- BAJAJ FINSERV",
        "AUTO DEBIT MANDATE",
        "TATA CAPITAL PERSONAL LOAN",
        "STANDING INSTRUCTION CAR LOAN",
    ]

    for narration in emi_keywords_tests:
        transactions = [
            create_sample_transaction(
                txn_date=date(2024, 1, 5),
                narration=narration,
                withdrawal_amt=10000.0,
                closing_balance=90000.0
            ),
        ]

        result = await analyzer.analyze_from_transactions(transactions)
        assert result.emi_outflow_monthly == 10000.0, \
            f"Failed to detect EMI with narration: {narration}"


@pytest.mark.asyncio
async def test_emi_no_detection(analyzer):
    """Test that non-EMI transactions are not counted."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="GROCERY SHOPPING",
            withdrawal_amt=5000.0,
            closing_balance=95000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="ATM WITHDRAWAL",
            withdrawal_amt=10000.0,
            closing_balance=85000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.emi_outflow_monthly == 0.0


# ============================================================================
# Bounce Count Tests
# ============================================================================

@pytest.mark.asyncio
async def test_bounce_count_basic(analyzer):
    """Test bounce detection with standard keywords."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="CHEQUE BOUNCE",
            withdrawal_amt=100.0,
            closing_balance=99900.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="ECS RETURN INSUFFICIENT FUNDS",
            withdrawal_amt=50.0,
            closing_balance=99850.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 2, 5),
            narration="NACH RETURN DISHONOURED",
            withdrawal_amt=75.0,
            closing_balance=99775.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.bounce_count_12m == 3


@pytest.mark.asyncio
async def test_bounce_count_various_keywords(analyzer):
    """Test bounce detection with various keyword patterns."""
    bounce_keywords = [
        "CHEQUE BOUNCE",
        "INWARD RETURN",
        "CHQ RETURN",
        "ECS RETURN",
        "NACH RETURN",
        "PAYMENT FAILED",
        "TRANSACTION REVERSED",
        "DISHONOURED",
        "INSUFFICIENT BALANCE",
        "UNPAID",
        "REJECT",
    ]

    for keyword in bounce_keywords:
        transactions = [
            create_sample_transaction(
                txn_date=date(2024, 1, 5),
                narration=f"PAYMENT {keyword}",
                withdrawal_amt=100.0,
                closing_balance=99900.0
            ),
        ]

        result = await analyzer.analyze_from_transactions(transactions)
        assert result.bounce_count_12m == 1, \
            f"Failed to detect bounce with keyword: {keyword}"


@pytest.mark.asyncio
async def test_bounce_count_zero(analyzer):
    """Test that clean statement has zero bounces."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY CREDIT",
            deposit_amt=50000.0,
            closing_balance=150000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="RENT PAYMENT",
            withdrawal_amt=20000.0,
            closing_balance=130000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.bounce_count_12m == 0


# ============================================================================
# Cash Deposit Ratio Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cash_deposit_ratio_basic(analyzer):
    """Test cash deposit ratio calculation."""
    transactions = [
        # Cash deposits: 10000 + 20000 = 30000
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="CASH DEPOSIT",
            deposit_amt=10000.0,
            closing_balance=110000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="BY CASH CREDIT",
            deposit_amt=20000.0,
            closing_balance=130000.0
        ),
        # Non-cash deposit: 50000
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="SALARY CREDIT",
            deposit_amt=50000.0,
            closing_balance=180000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Total credits = 80000
    # Cash deposits = 30000
    # Ratio = 30000 / 80000 = 0.375
    assert result.cash_deposit_ratio == 0.375


@pytest.mark.asyncio
async def test_cash_deposit_ratio_exclude_cash_credit_account(analyzer):
    """Test that 'CASH CREDIT A/C' is excluded from cash deposits."""
    transactions = [
        # This should NOT be counted as cash deposit
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="TRANSFER FROM CASH CREDIT A/C",
            deposit_amt=50000.0,
            closing_balance=150000.0
        ),
        # This SHOULD be counted
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="CASH DEPOSIT",
            deposit_amt=10000.0,
            closing_balance=160000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Total credits = 60000
    # Cash deposits = 10000 (only the second one)
    # Ratio = 10000 / 60000 = 0.1667
    assert abs(result.cash_deposit_ratio - 0.1667) < 0.0001


@pytest.mark.asyncio
async def test_cash_deposit_ratio_zero_cash(analyzer):
    """Test cash deposit ratio when there are no cash deposits."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY CREDIT",
            deposit_amt=50000.0,
            closing_balance=150000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="TRANSFER CREDIT",
            deposit_amt=10000.0,
            closing_balance=160000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.cash_deposit_ratio == 0.0


@pytest.mark.asyncio
async def test_cash_deposit_ratio_all_cash(analyzer):
    """Test cash deposit ratio when all deposits are cash."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="CASH DEPOSIT",
            deposit_amt=10000.0,
            closing_balance=110000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="BY CASH",
            deposit_amt=5000.0,
            closing_balance=115000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.cash_deposit_ratio == 1.0


# ============================================================================
# Peak and Min Balance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_peak_balance(analyzer):
    """Test peak balance calculation."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="DEPOSIT",
            deposit_amt=50000.0,
            closing_balance=100000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="DEPOSIT",
            deposit_amt=100000.0,
            closing_balance=200000.0  # Peak
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="WITHDRAWAL",
            withdrawal_amt=50000.0,
            closing_balance=150000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.peak_balance == 200000.0


@pytest.mark.asyncio
async def test_min_balance(analyzer):
    """Test minimum balance calculation."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="DEPOSIT",
            deposit_amt=50000.0,
            closing_balance=100000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="WITHDRAWAL",
            withdrawal_amt=80000.0,
            closing_balance=20000.0  # Minimum
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="DEPOSIT",
            deposit_amt=30000.0,
            closing_balance=50000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)
    assert result.min_balance == 20000.0


# ============================================================================
# Monthly Summary Tests
# ============================================================================

@pytest.mark.asyncio
async def test_monthly_summary(analyzer):
    """Test monthly summary breakdown."""
    transactions = [
        # January
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY",
            deposit_amt=50000.0,
            closing_balance=150000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="RENT",
            withdrawal_amt=20000.0,
            closing_balance=130000.0
        ),
        # February
        create_sample_transaction(
            txn_date=date(2024, 2, 5),
            narration="SALARY",
            deposit_amt=50000.0,
            closing_balance=180000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 2, 10),
            narration="CHEQUE BOUNCE",
            withdrawal_amt=100.0,
            closing_balance=179900.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    assert len(result.monthly_summary) == 2

    # January summary
    jan_summary = result.monthly_summary[0]
    assert jan_summary['month'] == '2024-01'
    assert jan_summary['credits'] == 50000.0
    assert jan_summary['debits'] == 20000.0
    assert jan_summary['closing_balance'] == 130000.0
    assert jan_summary['bounce_count'] == 0

    # February summary
    feb_summary = result.monthly_summary[1]
    assert feb_summary['month'] == '2024-02'
    assert feb_summary['credits'] == 50000.0
    assert feb_summary['debits'] == 100.0
    assert feb_summary['closing_balance'] == 179900.0
    assert feb_summary['bounce_count'] == 1


# ============================================================================
# Confidence Score Tests
# ============================================================================

@pytest.mark.asyncio
async def test_confidence_score_high(analyzer):
    """Test confidence score with good data quality."""
    # Create 100 transactions over 12 months with complete data
    transactions = []
    base_date = date(2024, 1, 1)

    for i in range(100):
        transactions.append(create_sample_transaction(
            txn_date=base_date + timedelta(days=i * 3),
            narration=f"TRANSACTION {i}",
            deposit_amt=1000.0 if i % 2 == 0 else 0.0,
            withdrawal_amt=0.0 if i % 2 == 0 else 500.0,
            closing_balance=50000.0 + (i * 100)
        ))

    result = await analyzer.analyze_from_transactions(transactions)

    # Should have high confidence:
    # - 100 transactions (30 points)
    # - ~10 months period (25 points)
    # - 100% data completeness (40 points)
    assert result.confidence > 0.8


@pytest.mark.asyncio
async def test_confidence_score_low(analyzer):
    """Test confidence score with poor data quality."""
    # Create only 5 transactions over 1 month with incomplete data
    transactions = [
        {
            'transactionDate': date(2024, 1, 1),
            'valueDate': date(2024, 1, 1),
            'narration': "TEST",
            'chequeRefNo': "",
            'withdrawalAmt': 0.0,
            'depositAmt': 0.0,
            'closingBalance': None,  # Incomplete data
        }
        for _ in range(5)
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    # Should have low confidence:
    # - 5 transactions (low score)
    # - 1 month period (low score)
    # - 0% data completeness (0 points)
    assert result.confidence < 0.3


# ============================================================================
# Edge Cases Tests
# ============================================================================

@pytest.mark.asyncio
async def test_single_transaction(analyzer):
    """Test analyzer with single transaction."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 1),
            narration="DEPOSIT",
            deposit_amt=50000.0,
            closing_balance=100000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    assert result.transaction_count == 1
    assert result.statement_period_months == 1
    assert result.avg_monthly_balance == 100000.0
    assert result.monthly_credit_avg == 50000.0
    assert result.monthly_debit_avg == 0.0


@pytest.mark.asyncio
async def test_transactions_with_none_values(analyzer):
    """Test analyzer handles None values gracefully."""
    transactions = [
        {
            'transactionDate': date(2024, 1, 1),
            'valueDate': date(2024, 1, 1),
            'narration': "TEST",
            'chequeRefNo': "",
            'withdrawalAmt': None,  # None value
            'depositAmt': None,  # None value
            'closingBalance': 50000.0,
        },
        create_sample_transaction(
            txn_date=date(2024, 1, 2),
            narration="DEPOSIT",
            deposit_amt=10000.0,
            closing_balance=60000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    assert result.transaction_count == 2
    # Should handle None values without crashing
    assert result.avg_monthly_balance is not None


@pytest.mark.asyncio
async def test_total_credits_and_debits(analyzer):
    """Test total credits and debits calculation."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY",
            deposit_amt=50000.0,
            closing_balance=150000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 10),
            narration="RENT",
            withdrawal_amt=20000.0,
            closing_balance=130000.0
        ),
        create_sample_transaction(
            txn_date=date(2024, 1, 15),
            narration="BONUS",
            deposit_amt=10000.0,
            closing_balance=140000.0
        ),
    ]

    result = await analyzer.analyze_from_transactions(transactions)

    assert result.total_credits_12m == 60000.0  # 50000 + 10000
    assert result.total_debits_12m == 20000.0


@pytest.mark.asyncio
async def test_epoch_millisecond_transactions_are_normalized(analyzer):
    """Test analyzer accepts Credilo-style epoch millisecond transaction dates."""
    transactions = [
        {
            "transactionDate": 1704067200000,  # 2024-01-01
            "valueDate": 1704067200000,
            "narration": "SALARY CREDIT",
            "chequeRefNo": "",
            "withdrawalAmt": 0,
            "depositAmt": "75,000.50",
            "closingBalance": "125000.75",
        },
        {
            "transactionDate": "1704585600000",  # 2024-01-07
            "valueDate": "1704585600000",
            "narration": "HDFC LOAN EMI",
            "chequeRefNo": "",
            "withdrawalAmt": "15,000",
            "depositAmt": 0,
            "closingBalance": 110000.75,
        },
    ]

    result = await analyzer.analyze_from_transactions(transactions, source="credilo_remote")

    assert result.transaction_count == 2
    assert result.statement_period_months == 1
    assert result.monthly_credit_avg == 75000.5
    assert result.monthly_debit_avg == 15000.0
    assert result.source == "credilo_remote"


@pytest.mark.asyncio
async def test_credilo_summary_metadata_is_preserved(analyzer):
    """Test credilo summary metadata is carried through analysis result."""
    transactions = [
        create_sample_transaction(
            txn_date=date(2024, 1, 5),
            narration="SALARY CREDIT",
            deposit_amt=50000.0,
            closing_balance=100000.0,
        )
    ]

    summary = {
        "statement_count": 1,
        "total_transactions": 42,
        "custom_average_balance": 98000.25,
    }
    result = await analyzer.analyze_from_transactions(
        transactions=transactions,
        source="credilo_remote",
        credilo_summary=summary,
    )

    assert result.source == "credilo_remote"
    assert result.credilo_summary.get("statement_count") == 1
    assert result.credilo_summary.get("total_transactions") == 42
    assert result.credilo_summary.get("custom_average_balance") == 98000.25
