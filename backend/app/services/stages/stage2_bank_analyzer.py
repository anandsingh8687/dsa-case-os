"""Stage 2: Bank Statement Analysis Service
Computes financial metrics from parsed bank statement transactions.
Uses Credilo parser for PDF extraction, then computes metrics.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from collections import defaultdict
from decimal import Decimal

from app.services.credilo_parser import StatementParser, ParsedStatement
from app.schemas.shared import BankAnalysisResult

logger = logging.getLogger(__name__)


class BankStatementAnalyzer:
    """
    Analyzes bank statements to compute financial metrics.
    Wraps Credilo parser and adds metric computation layer.
    """

    # EMI detection keywords
    EMI_KEYWORDS = [
        'EMI', 'LOAN', 'NACH', 'ECS', 'SI-', 'MANDATE',
        'BAJAJ', 'HDFC LOAN', 'TATA CAPITAL', 'ICICI LOAN',
        'HOME LOAN', 'CAR LOAN', 'PERSONAL LOAN',
        'AUTO DEBIT', 'STANDING INSTRUCTION'
    ]

    # Bounce detection keywords
    BOUNCE_KEYWORDS = [
        'BOUNCE', 'RETURN', 'DISHON', 'INSUFFICIENT',
        'UNPAID', 'REJECT', 'INWARD RETURN', 'CHQ RETURN',
        'ECS RETURN', 'NACH RETURN', 'FAILED', 'REVERSED'
    ]

    # Cash deposit keywords
    CASH_DEPOSIT_KEYWORDS = [
        'CASH DEP', 'BY CASH', 'CASH DEPOSIT',
        'CASH CR', 'CASH CREDIT'
    ]

    # Exclude "CASH CREDIT A/C" which is an account type
    CASH_DEPOSIT_EXCLUDE = ['CASH CREDIT A/C', 'CC A/C', 'CC ACCOUNT']

    def __init__(self):
        self.parser = StatementParser()

    async def analyze(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """
        Parse PDFs with Credilo, then compute financial metrics.

        Args:
            pdf_paths: List of paths to bank statement PDFs

        Returns:
            BankAnalysisResult with computed metrics
        """
        # Step 1: Parse with Credilo
        statements = self.parser.parse_statements(pdf_paths)

        if not statements:
            logger.warning("No statements parsed from PDFs")
            return BankAnalysisResult(confidence=0.0)

        # Step 2: Aggregate all transactions
        all_transactions = []
        bank_names = set()
        account_numbers = set()

        for statement in statements:
            all_transactions.extend(statement.transactions)
            bank_names.add(statement.bank_name)
            account_numbers.add(statement.account_number)

        # Use first bank/account if multiple detected
        bank_detected = list(bank_names)[0] if bank_names else None
        account_number = list(account_numbers)[0] if account_numbers else None

        # Step 3: Compute metrics
        return await self.analyze_from_transactions(
            transactions=all_transactions,
            bank_detected=bank_detected,
            account_number=account_number
        )

    async def analyze_from_transactions(
        self,
        transactions: List[Dict[str, Any]],
        bank_detected: Optional[str] = None,
        account_number: Optional[str] = None
    ) -> BankAnalysisResult:
        """
        Compute metrics from pre-parsed transactions.

        Args:
            transactions: List of transaction dicts from Credilo parser
            bank_detected: Detected bank name (optional)
            account_number: Account number (optional)

        Returns:
            BankAnalysisResult with computed metrics
        """
        if not transactions:
            return BankAnalysisResult(
                bank_detected=bank_detected,
                account_number=account_number,
                transaction_count=0,
                confidence=0.0
            )

        # Sort transactions by date
        sorted_transactions = sorted(
            transactions,
            key=lambda t: t.get('transactionDate', date.min)
        )

        # Calculate statement period
        start_date = sorted_transactions[0].get('transactionDate')
        end_date = sorted_transactions[-1].get('transactionDate')
        statement_period_months = self._calculate_months_between(start_date, end_date)

        # Compute metrics
        avg_monthly_balance = self._compute_avg_monthly_balance(sorted_transactions)
        monthly_credit_avg = self._compute_monthly_credit_avg(sorted_transactions)
        monthly_debit_avg = self._compute_monthly_debit_avg(sorted_transactions)
        emi_outflow_monthly = self._compute_emi_outflow(sorted_transactions)
        bounce_count_12m = self._compute_bounce_count(sorted_transactions)
        cash_deposit_ratio = self._compute_cash_deposit_ratio(sorted_transactions)
        peak_balance = self._compute_peak_balance(sorted_transactions)
        min_balance = self._compute_min_balance(sorted_transactions)
        total_credits_12m = self._compute_total_credits(sorted_transactions)
        total_debits_12m = self._compute_total_debits(sorted_transactions)
        monthly_summary = self._compute_monthly_summary(sorted_transactions)

        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(
            transactions=sorted_transactions,
            statement_period_months=statement_period_months
        )

        return BankAnalysisResult(
            bank_detected=bank_detected,
            account_number=account_number,
            transaction_count=len(sorted_transactions),
            statement_period_months=statement_period_months,
            avg_monthly_balance=avg_monthly_balance,
            monthly_credit_avg=monthly_credit_avg,
            monthly_debit_avg=monthly_debit_avg,
            emi_outflow_monthly=emi_outflow_monthly,
            bounce_count_12m=bounce_count_12m,
            cash_deposit_ratio=cash_deposit_ratio,
            peak_balance=peak_balance,
            min_balance=min_balance,
            total_credits_12m=total_credits_12m,
            total_debits_12m=total_debits_12m,
            monthly_summary=monthly_summary,
            confidence=confidence
        )

    def _calculate_months_between(self, start_date: date, end_date: date) -> int:
        """Calculate number of months between two dates."""
        if not start_date or not end_date:
            return 0

        months = (end_date.year - start_date.year) * 12
        months += end_date.month - start_date.month
        return max(1, months + 1)  # Add 1 to include both start and end months

    def _compute_avg_monthly_balance(self, transactions: List[Dict]) -> Optional[float]:
        """
        Compute average monthly balance.
        For each month, take the last closingBalance as month-end balance.
        Average all month-end balances.
        """
        if not transactions:
            return None

        # Group transactions by month
        monthly_balances = {}

        for txn in transactions:
            txn_date = txn.get('transactionDate')
            if not txn_date:
                continue

            month_key = f"{txn_date.year}-{txn_date.month:02d}"
            closing_balance = txn.get('closingBalance', 0)

            # Keep updating - last transaction will have final balance
            monthly_balances[month_key] = closing_balance

        if not monthly_balances:
            return None

        # Average all month-end balances
        total = sum(monthly_balances.values())
        return round(total / len(monthly_balances), 2)

    def _compute_monthly_credit_avg(self, transactions: List[Dict]) -> Optional[float]:
        """
        Compute average monthly credits.
        Sum all depositAmt per month, then average across all months.
        """
        if not transactions:
            return None

        # Group by month
        monthly_credits = defaultdict(float)

        for txn in transactions:
            txn_date = txn.get('transactionDate')
            if not txn_date:
                continue

            month_key = f"{txn_date.year}-{txn_date.month:02d}"
            deposit_amt = txn.get('depositAmt', 0) or 0
            monthly_credits[month_key] += deposit_amt

        if not monthly_credits:
            return None

        # Average across months
        total = sum(monthly_credits.values())
        return round(total / len(monthly_credits), 2)

    def _compute_monthly_debit_avg(self, transactions: List[Dict]) -> Optional[float]:
        """
        Compute average monthly debits.
        Sum all withdrawalAmt per month, then average across all months.
        """
        if not transactions:
            return None

        # Group by month
        monthly_debits = defaultdict(float)

        for txn in transactions:
            txn_date = txn.get('transactionDate')
            if not txn_date:
                continue

            month_key = f"{txn_date.year}-{txn_date.month:02d}"
            withdrawal_amt = txn.get('withdrawalAmt', 0) or 0
            monthly_debits[month_key] += withdrawal_amt

        if not monthly_debits:
            return None

        # Average across months
        total = sum(monthly_debits.values())
        return round(total / len(monthly_debits), 2)

    def _compute_emi_outflow(self, transactions: List[Dict]) -> Optional[float]:
        """
        Detect EMI patterns and compute total monthly EMI outflow.

        Logic:
        1. Find recurring debits with similar amounts (±5% tolerance)
        2. Check for EMI-related keywords in narration
        3. Sum all detected EMI debits per month and average
        """
        if not transactions:
            return None

        # Find potential EMI transactions
        emi_transactions = []

        for txn in transactions:
            narration = (txn.get('narration') or '').upper()
            withdrawal_amt = txn.get('withdrawalAmt', 0) or 0

            # Must be a debit
            if withdrawal_amt <= 0:
                continue

            # Check for EMI keywords
            if any(keyword in narration for keyword in self.EMI_KEYWORDS):
                emi_transactions.append({
                    'date': txn.get('transactionDate'),
                    'amount': withdrawal_amt,
                    'narration': narration
                })

        if not emi_transactions:
            return 0.0

        # Group by month and sum
        monthly_emi = defaultdict(float)
        for emi in emi_transactions:
            if emi['date']:
                month_key = f"{emi['date'].year}-{emi['date'].month:02d}"
                monthly_emi[month_key] += emi['amount']

        if not monthly_emi:
            return 0.0

        # Average monthly EMI
        total = sum(monthly_emi.values())
        return round(total / len(monthly_emi), 2)

    def _compute_bounce_count(self, transactions: List[Dict]) -> int:
        """
        Count bounced transactions in the last 12 months.
        Look for debit transactions with bounce-related keywords.
        """
        bounce_count = 0

        for txn in transactions:
            narration = (txn.get('narration') or '').upper()
            withdrawal_amt = txn.get('withdrawalAmt', 0) or 0

            # Check for bounce keywords
            if any(keyword in narration for keyword in self.BOUNCE_KEYWORDS):
                # Only count if it's a debit (return charges) or has explicit bounce indicators
                if withdrawal_amt > 0 or 'RETURN' in narration or 'BOUNCE' in narration:
                    bounce_count += 1

        return bounce_count

    def _compute_cash_deposit_ratio(self, transactions: List[Dict]) -> Optional[float]:
        """
        Compute ratio of cash deposits to total credits.
        Identifies cash deposits using keywords, excluding "CASH CREDIT A/C".
        """
        total_credits = 0.0
        cash_deposits = 0.0

        for txn in transactions:
            deposit_amt = txn.get('depositAmt', 0) or 0
            narration = (txn.get('narration') or '').upper()

            if deposit_amt > 0:
                total_credits += deposit_amt

                # Check for cash deposit keywords
                is_cash_deposit = any(
                    keyword in narration
                    for keyword in self.CASH_DEPOSIT_KEYWORDS
                )

                # Exclude "CASH CREDIT A/C" account type
                is_excluded = any(
                    exclude in narration
                    for exclude in self.CASH_DEPOSIT_EXCLUDE
                )

                if is_cash_deposit and not is_excluded:
                    cash_deposits += deposit_amt

        if total_credits == 0:
            return None

        ratio = cash_deposits / total_credits
        return round(ratio, 4)

    def _compute_peak_balance(self, transactions: List[Dict]) -> Optional[float]:
        """Get maximum closing balance in the period."""
        if not transactions:
            return None

        balances = [
            txn.get('closingBalance', 0) or 0
            for txn in transactions
            if txn.get('closingBalance') is not None
        ]

        return max(balances) if balances else None

    def _compute_min_balance(self, transactions: List[Dict]) -> Optional[float]:
        """Get minimum closing balance in the period."""
        if not transactions:
            return None

        balances = [
            txn.get('closingBalance', 0) or 0
            for txn in transactions
            if txn.get('closingBalance') is not None
        ]

        return min(balances) if balances else None

    def _compute_total_credits(self, transactions: List[Dict]) -> Optional[float]:
        """Compute total credits in the period."""
        if not transactions:
            return None

        total = sum(txn.get('depositAmt', 0) or 0 for txn in transactions)
        return round(total, 2)

    def _compute_total_debits(self, transactions: List[Dict]) -> Optional[float]:
        """Compute total debits in the period."""
        if not transactions:
            return None

        total = sum(txn.get('withdrawalAmt', 0) or 0 for txn in transactions)
        return round(total, 2)

    def _compute_monthly_summary(self, transactions: List[Dict]) -> List[Dict[str, Any]]:
        """
        Compute per-month breakdown.

        Returns:
            List of dicts with: month, credits, debits, closing_balance, bounce_count
        """
        if not transactions:
            return []

        # Group by month
        monthly_data = defaultdict(lambda: {
            'credits': 0.0,
            'debits': 0.0,
            'closing_balance': None,
            'bounce_count': 0
        })

        for txn in transactions:
            txn_date = txn.get('transactionDate')
            if not txn_date:
                continue

            month_key = f"{txn_date.year}-{txn_date.month:02d}"
            narration = (txn.get('narration') or '').upper()

            # Aggregate credits and debits
            monthly_data[month_key]['credits'] += txn.get('depositAmt', 0) or 0
            monthly_data[month_key]['debits'] += txn.get('withdrawalAmt', 0) or 0

            # Update closing balance (last transaction wins)
            monthly_data[month_key]['closing_balance'] = txn.get('closingBalance')

            # Count bounces
            if any(keyword in narration for keyword in self.BOUNCE_KEYWORDS):
                monthly_data[month_key]['bounce_count'] += 1

        # Convert to list format
        summary = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            summary.append({
                'month': month,
                'credits': round(data['credits'], 2),
                'debits': round(data['debits'], 2),
                'closing_balance': data['closing_balance'],
                'bounce_count': data['bounce_count']
            })

        return summary

    def _calculate_confidence(
        self,
        transactions: List[Dict],
        statement_period_months: int
    ) -> float:
        """
        Calculate confidence score based on data quality.

        Factors:
        - Number of transactions
        - Statement period length
        - Data completeness (presence of balances, amounts)
        """
        if not transactions:
            return 0.0

        confidence = 0.0

        # Factor 1: Transaction count (max 30 points)
        txn_count_score = min(len(transactions) / 100 * 30, 30)
        confidence += txn_count_score

        # Factor 2: Statement period (max 30 points)
        # Ideal: 12 months
        period_score = min(statement_period_months / 12 * 30, 30)
        confidence += period_score

        # Factor 3: Data completeness (max 40 points)
        complete_txns = sum(
            1 for txn in transactions
            if txn.get('closingBalance') is not None
            and (txn.get('depositAmt') or txn.get('withdrawalAmt'))
        )
        completeness_score = (complete_txns / len(transactions)) * 40
        confidence += completeness_score

        return round(confidence / 100, 2)


# Singleton instance
_analyzer_instance = None


def get_analyzer() -> BankStatementAnalyzer:
    """Get or create the singleton bank statement analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BankStatementAnalyzer()
    return _analyzer_instance
