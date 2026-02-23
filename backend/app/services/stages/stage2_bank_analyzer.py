"""Stage 2: Bank Statement Analysis Service
Computes financial metrics from parsed bank statement transactions.
Uses Credilo parser for PDF extraction, then computes metrics.
"""
import logging
import asyncio
import io
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timezone
from collections import defaultdict
from decimal import Decimal

import pandas as pd

from app.core.config import settings
from app.services.credilo_api_client import CrediloApiClient, CrediloApiError
from app.services.credilo_parser import StatementParser
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
        self.credilo_client = CrediloApiClient()
        self.use_remote = bool(settings.CREDILO_USE_REMOTE_IN_EXTRACTION)
        self.allow_local_fallback = bool(settings.CREDILO_FALLBACK_TO_LOCAL)

    async def analyze(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """
        Parse PDFs with Credilo, then compute financial metrics.

        Args:
            pdf_paths: List of paths to bank statement PDFs

        Returns:
            BankAnalysisResult with computed metrics
        """
        if self.use_remote:
            try:
                return await self._analyze_with_remote_credilo(pdf_paths)
            except Exception as exc:
                logger.warning("Remote Credilo preview failed: %s", exc)
                try:
                    return await self._analyze_with_remote_process(pdf_paths)
                except Exception as process_exc:
                    logger.warning("Remote Credilo process fallback failed: %s", process_exc)
                    if not self.allow_local_fallback:
                        return BankAnalysisResult(confidence=0.0, source="credilo_remote")

        return await self._analyze_with_local_parser(pdf_paths)

    async def _analyze_with_local_parser(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """Analyze statements using local parser fallback."""
        # Offload parser work so endpoint-level asyncio timeouts can actually preempt long runs.
        statements = await asyncio.to_thread(self.parser.parse_statements, pdf_paths)

        if not statements:
            logger.warning("No statements parsed from PDFs")
            return BankAnalysisResult(confidence=0.0, source="local_parser")

        all_transactions = []
        bank_names = set()
        account_numbers = set()

        for statement in statements:
            all_transactions.extend(statement.transactions)
            bank_names.add(statement.bank_name)
            account_numbers.add(statement.account_number)

        bank_detected = list(bank_names)[0] if bank_names else None
        account_number = list(account_numbers)[0] if account_numbers else None

        return await self.analyze_from_transactions(
            transactions=all_transactions,
            bank_detected=bank_detected,
            account_number=account_number,
            source="local_parser",
        )

    async def _analyze_with_remote_credilo(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """Analyze statements using remote Credilo preview endpoint."""
        if not self.credilo_client.is_configured():
            raise CrediloApiError("Credilo preview URL is not configured")

        payload = await self.credilo_client.process_preview(pdf_paths)
        transactions, bank_detected, account_number, credilo_summary = self._extract_remote_payload(payload)

        if not transactions:
            raise CrediloApiError("Credilo preview returned no transactions")

        return await self.analyze_from_transactions(
            transactions=transactions,
            bank_detected=bank_detected,
            account_number=account_number,
            source="credilo_remote",
            credilo_summary=credilo_summary,
        )

    async def _analyze_with_remote_process(self, pdf_paths: List[str]) -> BankAnalysisResult:
        """Fallback analyzer using Credilo /api/process XLSX output."""
        workbook_bytes = await self.credilo_client.process_excel(pdf_paths)
        transactions, bank_detected, account_number, credilo_summary = self._extract_transactions_from_remote_workbook(
            workbook_bytes
        )

        if not transactions:
            raise CrediloApiError("Credilo process fallback produced no transactions")

        return await self.analyze_from_transactions(
            transactions=transactions,
            bank_detected=bank_detected,
            account_number=account_number,
            source="credilo_process_xlsx",
            credilo_summary=credilo_summary,
        )

    async def analyze_from_transactions(
        self,
        transactions: List[Dict[str, Any]],
        bank_detected: Optional[str] = None,
        account_number: Optional[str] = None,
        source: str = "unknown",
        credilo_summary: Optional[Dict[str, Any]] = None,
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
        normalized_transactions = self._normalize_transactions(transactions)

        if not normalized_transactions:
            return BankAnalysisResult(
                bank_detected=bank_detected,
                account_number=account_number,
                transaction_count=0,
                confidence=0.0,
                source=source,
                credilo_summary=credilo_summary or {},
            )

        # Sort transactions by date
        sorted_transactions = sorted(
            normalized_transactions,
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
            confidence=confidence,
            source=source,
            credilo_summary=credilo_summary or {},
        )

    def _extract_remote_payload(
        self,
        payload: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str], Dict[str, Any]]:
        """Extract and flatten transactions from Credilo preview payload."""
        statements = payload.get("statements") if isinstance(payload, dict) else []
        if not isinstance(statements, list):
            statements = []

        all_transactions: List[Dict[str, Any]] = []
        bank_detected: Optional[str] = None
        account_number: Optional[str] = None

        for statement in statements:
            if not isinstance(statement, dict):
                continue

            basic_info = statement.get("basicInfo") or {}
            bank_detected = bank_detected or statement.get("bank") or basic_info.get("bankName")
            account_number = account_number or statement.get("accountNumber") or basic_info.get("accountNumber")

            statement_tx = statement.get("transactions") or []
            if isinstance(statement_tx, list):
                all_transactions.extend(statement_tx)

        first_statement = statements[0] if statements and isinstance(statements[0], dict) else {}
        basic_info = first_statement.get("basicInfo") or {}
        cam = first_statement.get("camAnalysisData") or {}
        grand = first_statement.get("grandTotal") or {}

        credilo_summary = {
            "statement_count": len(statements),
            "total_input_files": self._to_int(payload.get("totalInputFiles")),
            "total_transactions": self._to_int(payload.get("totalTransactions")) or len(all_transactions),
            "period_start": basic_info.get("periodStart"),
            "period_end": basic_info.get("periodEnd"),
            "average_balance": self._to_optional_float(cam.get("averageBalance")),
            "custom_average_balance": self._to_optional_float(cam.get("customAverageBalance")),
            "custom_average_balance_last_three_month": self._to_optional_float(
                cam.get("customAverageBalanceLastThreeMonth")
            ),
            "credit_transactions_amount": self._to_optional_float(grand.get("creditTransactionsAmount")),
            "debit_transactions_amount": self._to_optional_float(grand.get("debitTransactionsAmount")),
            "net_credit_transactions_amount": self._to_optional_float(grand.get("netCreditTransactionsAmount")),
            "net_debit_transactions_amount": self._to_optional_float(grand.get("netDebitTransactionsAmount")),
            "no_of_emi": self._to_int(grand.get("noOfEMI")),
            "total_emi_amount": self._to_optional_float(grand.get("totalEMIAmount")),
            "no_of_emi_bounce": self._to_int(grand.get("noOfEMIBounce")),
            "total_emi_bounce_amount": self._to_optional_float(grand.get("totalEMIBounceAmount")),
            "no_of_loan_disbursal": self._to_int(grand.get("noOfLoanDisbursal")),
            "loan_disbursal_amount": self._to_optional_float(grand.get("loanDisbursalAmount")),
        }

        return all_transactions, bank_detected, account_number, credilo_summary

    def _extract_transactions_from_remote_workbook(
        self,
        workbook_bytes: bytes,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str], Dict[str, Any]]:
        """Parse Credilo process XLSX into normalized transaction rows."""
        excel = pd.ExcelFile(io.BytesIO(workbook_bytes))
        all_transactions: List[Dict[str, Any]] = []
        bank_detected: Optional[str] = None
        account_number: Optional[str] = None

        for sheet in excel.sheet_names:
            try:
                dataframe = pd.read_excel(excel, sheet_name=sheet)
            except Exception:
                continue

            columns_map = {str(col).strip().lower(): col for col in dataframe.columns}
            date_col = columns_map.get("transactiondate") or columns_map.get("transaction date")
            narration_col = columns_map.get("narration")
            withdrawal_col = columns_map.get("withdrawalamt") or columns_map.get("withdrawal amt")
            deposit_col = columns_map.get("depositamt") or columns_map.get("deposit amt")
            closing_col = columns_map.get("closingbalance") or columns_map.get("closing balance")

            if not date_col or not narration_col:
                continue

            if not bank_detected:
                bank_detected = str(sheet).split("_")[0] if "_" in str(sheet) else str(sheet)
            if not account_number:
                sheet_parts = str(sheet).split("_")
                if len(sheet_parts) > 1 and sheet_parts[-1].isdigit():
                    account_number = sheet_parts[-1]

            for _, row in dataframe.iterrows():
                transaction_date = row.get(date_col)
                narration = row.get(narration_col)
                if pd.isna(transaction_date) and pd.isna(narration):
                    continue

                transaction = {
                    "transactionDate": transaction_date,
                    "narration": "" if pd.isna(narration) else str(narration),
                    "withdrawalAmt": None if withdrawal_col is None or pd.isna(row.get(withdrawal_col)) else row.get(withdrawal_col),
                    "depositAmt": None if deposit_col is None or pd.isna(row.get(deposit_col)) else row.get(deposit_col),
                    "closingBalance": None if closing_col is None or pd.isna(row.get(closing_col)) else row.get(closing_col),
                }
                all_transactions.append(transaction)

        credilo_summary = {
            "statement_count": len(excel.sheet_names),
            "total_transactions": len(all_transactions),
        }

        return all_transactions, bank_detected, account_number, credilo_summary

    def _normalize_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize parser transactions to expected analyzer schema."""
        normalized = []
        for txn in transactions or []:
            if not isinstance(txn, dict):
                continue

            transaction_date = self._coerce_to_date(txn.get("transactionDate") or txn.get("valueDate"))
            if not transaction_date:
                continue

            normalized.append(
                {
                    "transactionDate": transaction_date,
                    "valueDate": self._coerce_to_date(txn.get("valueDate")) or transaction_date,
                    "narration": str(txn.get("narration") or "").strip(),
                    "chequeRefNo": str(txn.get("chequeRefNo") or txn.get("cheque") or "").strip(),
                    "withdrawalAmt": self._to_float(txn.get("withdrawalAmt")),
                    "depositAmt": self._to_float(txn.get("depositAmt")),
                    "closingBalance": self._to_optional_float(txn.get("closingBalance")),
                }
            )

        return normalized

    def _coerce_to_date(self, value: Any) -> Optional[date]:
        """Convert parser date values to date object."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, (int, float, Decimal)):
            raw = float(value)
            if raw <= 0:
                return None

            # Credilo uses epoch milliseconds.
            if raw > 10_000_000_000:
                raw = raw / 1000.0

            try:
                return datetime.fromtimestamp(raw, tz=timezone.utc).date()
            except (OSError, OverflowError, ValueError):
                return None

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None

            if text.isdigit():
                return self._coerce_to_date(int(text))

            for fmt in (
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%d %b %Y",
                "%d %B %Y",
            ):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    continue

            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            except ValueError:
                return None

        return None

    def _to_optional_float(self, value: Any) -> Optional[float]:
        """Convert parser number-like values to float, preserving None."""
        if value is None or value == "":
            return None
        return self._to_float(value)

    def _to_float(self, value: Any) -> float:
        """Convert parser number-like values to float."""
        if value is None or value == "":
            return 0.0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _to_int(self, value: Any) -> int:
        """Convert parser number-like values to int."""
        if value is None or value == "":
            return 0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _calculate_months_between(self, start_date: date, end_date: date) -> int:
        """Calculate number of months between two dates."""
        if not start_date or not end_date:
            return 0

        months = (end_date.year - start_date.year) * 12
        months += end_date.month - start_date.month
        return max(1, months + 1)  # Add 1 to include both start and end months

    def _compute_avg_monthly_balance(self, transactions: List[Dict]) -> Optional[float]:
        """
        Compute average monthly balance using 5th/15th/25th checkpoint method.

        For each month:
        - pick closest known balance at each checkpoint day (5, 15, 25)
        - average those three balances to get monthly average
        Across months:
        - average monthly averages
        """
        if not transactions:
            return None

        monthly_entries = defaultdict(list)

        for txn in transactions:
            txn_date = txn.get('transactionDate')
            closing_balance = txn.get('closingBalance')
            if not txn_date:
                continue
            if closing_balance is None:
                continue
            month_key = f"{txn_date.year}-{txn_date.month:02d}"
            monthly_entries[month_key].append((txn_date, float(closing_balance)))

        if not monthly_entries:
            return None

        checkpoint_days = (5, 15, 25)
        monthly_checkpoint_averages = []

        for month_key in sorted(monthly_entries.keys()):
            entries = sorted(monthly_entries[month_key], key=lambda item: item[0])
            checkpoint_values = []

            for day in checkpoint_days:
                prior_or_same = [bal for dt, bal in entries if dt.day <= day]
                if prior_or_same:
                    checkpoint_values.append(prior_or_same[-1])
                    continue

                # If no transaction before the checkpoint day, use first available of the month.
                checkpoint_values.append(entries[0][1])

            if checkpoint_values:
                monthly_checkpoint_averages.append(sum(checkpoint_values) / len(checkpoint_values))

        if not monthly_checkpoint_averages:
            return None

        return round(sum(monthly_checkpoint_averages) / len(monthly_checkpoint_averages), 2)

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
        Detect EMI patterns and compute current monthly EMI outflow.

        Logic:
        1. Identify EMI-related debit transactions via narration keywords
        2. Sum EMI debits month-wise
        3. Return latest month's EMI sum (not average across months)
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

        latest_month = sorted(monthly_emi.keys())[-1]
        return round(monthly_emi[latest_month], 2)

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
