"""CIBIL report parser for extracting credit features from OCR/native text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional


def _to_number(value: str) -> Optional[float]:
    if not value:
        return None
    cleaned = value.replace(",", "").replace("₹", "").strip()
    if cleaned in {"-", "NA", "N/A", ""}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


class CibilReportParser:
    """Parse important credit metrics from mixed-format CIBIL reports."""

    def parse(self, text: str) -> Dict[str, Optional[float | int | str]]:
        normalized = self._normalize_text(text)

        report_date = self._extract_report_date(normalized)
        cibil_score = self._extract_score(normalized)
        active_loans = self._extract_active_loans(normalized)
        overdue_count = self._extract_overdue_count(normalized)
        enquiry_count_6m = self._extract_enquiry_count_6m(normalized, report_date)

        total_outstanding = self._extract_total_outstanding(normalized)

        return {
            "cibil_score": cibil_score,
            "active_loan_count": active_loans,
            "overdue_count": overdue_count,
            "enquiry_count_6m": enquiry_count_6m,
            "cibil_report_date": report_date.isoformat() if report_date else None,
            "total_current_outstanding": total_outstanding,
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text or ""
        text = text.replace("\u200b", "")
        text = text.replace("\r", "\n")
        return text

    def _extract_report_date(self, text: str) -> Optional[date]:
        patterns = [
            r"Report Date\s*[:\-]\s*(\d{2}[/-]\d{2}[/-]\d{4})",
            r"Date\s*[:\-]\s*(\d{2}[/-]\d{2}[/-]\d{4})",
            r"as of Date\s*[:\-]\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                dt = _parse_date(match.group(1))
                if dt:
                    return dt
        return None

    def _extract_score(self, text: str) -> Optional[int]:
        patterns = [
            r"Your\s+CIBIL\s+Score\s+is\s+(\d{3})",
            r"CIBIL\s*SCORE\s*[:\-]?\s*([3-9]\d{2})",
            r"(?:CIBIL\s+Score|Credit\s+Score|Score)\s*(?:is|:)?\s*(\d{3})",
            r"Score\s*Value\s*[:\-]?\s*([3-9]\d{2})",
            r"\b([3-9]\d{2})\s*/\s*900\b",
            r"\n\s*([3-9]\d{2})\s*\n\s*(?:GOOD|FAIR|POOR|VERY\s+GOOD|EXCELLENT)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    score = int(match.group(1))
                    if 300 <= score <= 900:
                        return score
                except ValueError:
                    continue

        return None

    def _extract_active_loans(self, text: str) -> Optional[int]:
        patterns = [
            r"(\d+)\s+Active\s+Loans",
            r"Active\s+Accounts?\s*[:\-]?\s*(\d+)",
            r"Total\s+Active\s+Loans?\s*[:\-]?\s*(\d+)",
            r"Active\s+Loan\s+Count\s*[:\-]?\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))

        blocks = re.split(r"\bACCOUNT\s+DETAILS\b", text, flags=re.IGNORECASE)
        if len(blocks) <= 1:
            return None

        active_count = 0
        for block in blocks[1:]:
            closed_match = re.search(r"Date\s+Closed\s+([^\n]+)", block, flags=re.IGNORECASE)
            if not closed_match:
                continue
            closed_val = closed_match.group(1).strip().upper()
            if closed_val in {"-", "NA", "N/A"}:
                active_count += 1

        return active_count if active_count > 0 else None

    def _extract_overdue_count(self, text: str) -> Optional[int]:
        patterns = [
            r"Overdue\s+Payments\s+(\d+)",
            r"No\.?\s*of\s*Accounts?\s*with\s*Overdue\s*[:\-]?\s*(\d+)",
            r"Accounts?\s+With\s+Overdue\s*[:\-]?\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))

        blocks = re.split(r"\bACCOUNT\s+DETAILS\b", text, flags=re.IGNORECASE)
        if len(blocks) <= 1:
            return None

        overdue_accounts = 0
        for block in blocks[1:]:
            amount_match = re.search(r"Amount\s+Overdue\s+([^\n]+)", block, flags=re.IGNORECASE)
            if not amount_match:
                continue
            amount = _to_number(amount_match.group(1))
            if amount and amount > 0:
                overdue_accounts += 1

        if overdue_accounts > 0:
            return overdue_accounts
        return 0

    def _extract_enquiry_count_6m(self, text: str, report_date: Optional[date]) -> Optional[int]:
        summary_patterns = [
            r"Recent\s+Enquiries(?:\s+last\s+\d+\s+months?)?\s*[:\-]?\s*(\d{1,3})\b",
            r"Recent\s+Enquiries(?:\s*\n|\s)+(?:last\s+\d+\s+months?\s*)?(\d{1,3})\b",
            r"Enquiries\s+in\s+last\s+(?:3|6)\s+months?\s*[:\-]?\s*(\d{1,3})\b",
            r"Total\s+Enquiries\s*\(?(?:last\s+6\s+months?)\)?\s*[:\-]?\s*(\d{1,3})\b",
            r"Enquiries\s*\(6M\)\s*[:\-]?\s*(\d{1,3})\b",
        ]
        for pattern in summary_patterns:
            summary = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if summary:
                count = int(summary.group(1))
                if 0 <= count <= 500:
                    return count

        section_counts: List[int] = []

        for start_match in re.finditer(r"Credit\s+Enquiries", text, flags=re.IGNORECASE):
            end_match = re.search(
                r"(Summary\s*:\s*Credit\s+Accounts|ALL\s+ACCOUNTS|ACCOUNT\s+DETAILS)",
                text[start_match.end():],
                flags=re.IGNORECASE,
            )
            if end_match:
                section = text[start_match.end(): start_match.end() + end_match.start()]
            else:
                section = text[start_match.end(): start_match.end() + 15000]

            date_strings = re.findall(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", section)
            parsed_dates = [d for d in (_parse_date(ds) for ds in date_strings) if d is not None]
            if not parsed_dates:
                continue

            base_date = report_date or max(parsed_dates)
            lower_bound = base_date - timedelta(days=183)
            count_6m = sum(1 for d in parsed_dates if lower_bound <= d <= base_date)
            if count_6m > 0:
                section_counts.append(count_6m)

        if section_counts:
            return max(section_counts)
        return None

    def _extract_total_outstanding(self, text: str) -> Optional[float]:
        patterns = [
            r"Current\s+Outstanding\s+₹\s*([0-9,]+(?:\.\d+)?)",
            r"Current\s+Balance\s+₹\s*([0-9,]+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                val = _to_number(match.group(1))
                if val is not None:
                    return val
        return None


_cibil_parser_instance: Optional[CibilReportParser] = None


def get_cibil_report_parser() -> CibilReportParser:
    global _cibil_parser_instance
    if _cibil_parser_instance is None:
        _cibil_parser_instance = CibilReportParser()
    return _cibil_parser_instance
