"""Credilo Bank Statement Parser
Mock implementation of the Credilo parser for extracting transactions from bank PDFs.
In production, this would be replaced with the actual Credilo parser_engine.py.
"""
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class ParsedStatement:
    """Represents a parsed bank statement with transactions."""
    bank_name: str
    account_number: str
    transactions: List[Dict[str, Any]]


class StatementParser:
    """
    Mock Credilo parser for bank statement PDF extraction.
    Supports 14+ Indian banks: HDFC, SBI, ICICI, Axis, Kotak, BOB, PNB, etc.
    """

    # Bank detection patterns
    BANK_PATTERNS = {
        'HDFC': r'HDFC\s*BANK',
        'SBI': r'STATE\s*BANK\s*OF\s*INDIA|SBI',
        'ICICI': r'ICICI\s*BANK',
        'AXIS': r'AXIS\s*BANK',
        'KOTAK': r'KOTAK\s*MAHINDRA\s*BANK',
        'BOB': r'BANK\s*OF\s*BARODA',
        'PNB': r'PUNJAB\s*NATIONAL\s*BANK|PNB',
        'CANARA': r'CANARA\s*BANK',
        'UNION': r'UNION\s*BANK',
        'INDIAN': r'INDIAN\s*BANK',
        'BOI': r'BANK\s*OF\s*INDIA',
        'IDBI': r'IDBI\s*BANK',
        'YES': r'YES\s*BANK',
        'INDUSIND': r'INDUSIND\s*BANK',
    }

    def __init__(self):
        self.confidence_threshold = 0.7

    def parse_statement(self, pdf_path: str) -> ParsedStatement:
        """
        Parse a single bank statement PDF.

        Args:
            pdf_path: Path to the bank statement PDF

        Returns:
            ParsedStatement with bank name, account number, and transactions
        """
        statements = self.parse_statements([pdf_path])
        return statements[0] if statements else None

    def parse_statements(self, pdf_paths: List[str]) -> List[ParsedStatement]:
        """
        Parse multiple bank statement PDFs.

        Args:
            pdf_paths: List of paths to bank statement PDFs

        Returns:
            List of ParsedStatement objects
        """
        all_statements = []

        for pdf_path in pdf_paths:
            try:
                statement = self._parse_single_pdf(pdf_path)
                if statement:
                    all_statements.append(statement)
            except Exception as e:
                logger.error(f"Error parsing {pdf_path}: {str(e)}", exc_info=True)
                continue

        return all_statements

    def _parse_single_pdf(self, pdf_path: str) -> Optional[ParsedStatement]:
        """Parse a single PDF and extract transactions."""
        with pdfplumber.open(pdf_path) as pdf:
            # Extract text from all pages
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() or ""

            # Detect bank
            bank_name = self._detect_bank(full_text)
            if not bank_name:
                logger.warning(f"Could not detect bank in {pdf_path}")
                bank_name = "UNKNOWN"

            # Extract account number
            account_number = self._extract_account_number(full_text)

            # Extract transactions based on bank format
            transactions = self._extract_transactions(full_text, bank_name)

            if not transactions:
                logger.warning(f"No transactions extracted from {pdf_path}")
                return None

            return ParsedStatement(
                bank_name=bank_name,
                account_number=account_number or "UNKNOWN",
                transactions=transactions
            )

    def _detect_bank(self, text: str) -> Optional[str]:
        """Detect the bank from PDF text."""
        text_upper = text.upper()

        for bank, pattern in self.BANK_PATTERNS.items():
            if re.search(pattern, text_upper, re.IGNORECASE):
                return bank

        return None

    def _extract_account_number(self, text: str) -> Optional[str]:
        """Extract account number from PDF text."""
        # Common patterns for account numbers
        patterns = [
            r'A/?C\s*(?:NO|NUMBER|#)?[\s:]*(\d{10,18})',
            r'ACCOUNT\s*(?:NO|NUMBER|#)?[\s:]*(\d{10,18})',
            r'A/C\s*NO[\s:]*(\d{10,18})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_transactions(self, text: str, bank_name: str) -> List[Dict[str, Any]]:
        """
        Extract transactions from statement text.
        This is a simplified parser - real Credilo has bank-specific parsers.

        Returns list of dicts with keys:
        - transactionDate: date of transaction
        - valueDate: value date
        - narration: description
        - chequeRefNo: cheque/ref number
        - withdrawalAmt: debit amount (float)
        - depositAmt: credit amount (float)
        - closingBalance: balance after transaction (float)
        """
        transactions = []

        # Split text into lines
        lines = text.split('\n')

        # Transaction pattern (simplified)
        # Typically: Date | Description | Cheque# | Debit | Credit | Balance
        # Example: 01/01/2024 ATM WDL 123456 5000.00 0.00 45000.00

        for line in lines:
            transaction = self._parse_transaction_line(line)
            if transaction:
                transactions.append(transaction)

        return transactions

    def _parse_transaction_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single transaction line."""
        # Try to extract date (DD/MM/YYYY or DD-MM-YYYY)
        date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', line)
        if not date_match:
            return None

        transaction_date_str = date_match.group(1).replace('-', '/')

        try:
            transaction_date = datetime.strptime(transaction_date_str, '%d/%m/%Y').date()
        except ValueError:
            return None

        # Extract amounts (looking for patterns like 1,234.56 or 1234.56)
        amount_pattern = r'(\d{1,3}(?:,\d{3})*\.?\d{0,2})'
        amounts = re.findall(amount_pattern, line)

        if len(amounts) < 2:
            return None

        # Clean amounts
        amounts = [float(amt.replace(',', '')) for amt in amounts]

        # Try to determine which is debit, credit, balance
        # Typically: debit, credit, balance (or credit, debit, balance)
        withdrawal_amt = 0.0
        deposit_amt = 0.0
        closing_balance = 0.0

        if len(amounts) >= 3:
            # Assume: first is debit, second is credit, third is balance
            # OR: first is credit, second is debit, third is balance
            # We'll use a heuristic: balance is usually the largest
            balance_idx = amounts.index(max(amounts))

            if balance_idx == 2:
                withdrawal_amt = amounts[0]
                deposit_amt = amounts[1]
                closing_balance = amounts[2]
            elif balance_idx == 1:
                deposit_amt = amounts[0]
                closing_balance = amounts[1]
            elif balance_idx == 0:
                closing_balance = amounts[0]
                if len(amounts) > 1:
                    withdrawal_amt = amounts[1]
        elif len(amounts) == 2:
            # Assume: amount, balance
            closing_balance = amounts[1]
            # Check if transaction is debit or credit based on keywords
            if any(keyword in line.upper() for keyword in ['DEBIT', 'WD', 'WDL', 'ATM', 'WITHDRAWAL', 'TRANSFER TO']):
                withdrawal_amt = amounts[0]
            else:
                deposit_amt = amounts[0]

        # Extract narration (text between date and first amount)
        narration_match = re.search(f'{transaction_date_str}(.+?){amount_pattern}', line)
        narration = narration_match.group(1).strip() if narration_match else line

        # Extract cheque/ref number if present
        cheque_match = re.search(r'(?:CHQ|CHEQUE|REF|UPI)[\s:]*(\d+)', line, re.IGNORECASE)
        cheque_ref_no = cheque_match.group(1) if cheque_match else ""

        return {
            'transactionDate': transaction_date,
            'valueDate': transaction_date,  # Simplified: same as transaction date
            'narration': narration[:200],  # Limit narration length
            'chequeRefNo': cheque_ref_no,
            'withdrawalAmt': withdrawal_amt,
            'depositAmt': deposit_amt,
            'closingBalance': closing_balance,
        }
