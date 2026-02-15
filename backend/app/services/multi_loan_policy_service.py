"""Service for PL/HL lender policy knowledge base and quick scan evaluation."""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


LoanType = Literal["PL", "HL"]
ApplicantType = Literal["salaried", "self_employed"]


def _parse_pct(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _parse_rate_midpoint(value: Optional[str], default: float) -> float:
    if not value:
        return default
    nums = re.findall(r"(\d+(?:\.\d+)?)", value)
    if not nums:
        return default
    points = [float(item) for item in nums]
    return (min(points) + max(points)) / 2.0


def _loan_label(loan_type: str) -> str:
    return {
        "PL": "Personal Loan",
        "HL": "Home Loan",
    }.get(loan_type, loan_type)


class MultiLoanPolicyService:
    def __init__(self, data_path: Path):
        self.data_path = data_path

    @lru_cache(maxsize=1)
    def _load(self) -> Dict[str, Any]:
        if not self.data_path.exists():
            return {"policies": []}
        with self.data_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {"policies": []}
        if not isinstance(payload.get("policies"), list):
            payload["policies"] = []
        return payload

    def stats(self) -> Dict[str, Any]:
        policies = self._load().get("policies", [])
        return {
            "version": self._load().get("version"),
            "source_document": self._load().get("source_document"),
            "total": len(policies),
            "by_loan_type": {
                "PL": sum(1 for row in policies if row.get("loan_type") == "PL"),
                "HL": sum(1 for row in policies if row.get("loan_type") == "HL"),
            },
        }

    def detect_applicant_type(self, raw_value: str) -> ApplicantType:
        value = (raw_value or "").strip().lower()
        salaried_markers = ["salary", "salaried", "gov", "mnc", "private job", "employed"]
        for marker in salaried_markers:
            if marker in value:
                return "salaried"
        return "self_employed"

    def evaluate(
        self,
        loan_type: LoanType,
        cibil_score: int,
        monthly_income_or_turnover: float,
        vintage_or_experience: float,
        entity_type_or_employer: str,
    ) -> Dict[str, Any]:
        policies = [
            row for row in self._load().get("policies", [])
            if row.get("loan_type") == loan_type
        ]

        applicant_type = self.detect_applicant_type(entity_type_or_employer)
        scoped_policies = [row for row in policies if row.get("applicant_type") == applicant_type]
        # fallback if applicant-specific rows are missing
        if not scoped_policies:
            scoped_policies = policies

        monthly_income = float(monthly_income_or_turnover)
        # guardrail: if user enters income in Lakhs by mistake, normalize to INR for PL/HL
        if monthly_income < 1000:
            monthly_income = monthly_income * 100000
        annual_income = monthly_income * 12

        passed: List[Dict[str, Any]] = []
        rejection_reasons: List[str] = []

        for policy in scoped_policies:
            min_cibil = int(policy.get("min_cibil") or 0)
            min_income_monthly = policy.get("min_income_monthly")
            min_income_annual = policy.get("min_income_annual")
            min_vintage = policy.get("business_vintage_years") if applicant_type == "self_employed" else None

            fails = []
            if min_cibil and cibil_score < min_cibil:
                fails.append(f"CIBIL {cibil_score} < required {min_cibil}")

            if min_income_monthly and monthly_income < float(min_income_monthly):
                fails.append(f"Income ₹{monthly_income:,.0f}/mo < required ₹{float(min_income_monthly):,.0f}/mo")
            if min_income_annual and annual_income < float(min_income_annual):
                fails.append(f"Income ₹{annual_income:,.0f}/yr < required ₹{float(min_income_annual):,.0f}/yr")

            if min_vintage and vintage_or_experience < float(min_vintage):
                fails.append(f"Business vintage {vintage_or_experience}y < required {float(min_vintage)}y")

            if fails:
                rejection_reasons.extend([f"{policy.get('lender_name')}: {item}" for item in fails[:1]])
                continue

            # Score model tuned for quick directional ranking.
            cibil_headroom = max(0, cibil_score - min_cibil) if min_cibil else 0
            income_target = float(min_income_monthly) if min_income_monthly else (float(min_income_annual) / 12.0 if min_income_annual else monthly_income)
            income_ratio = (monthly_income / income_target) if income_target > 0 else 1.0
            income_boost = min(25.0, max(0.0, (income_ratio - 1.0) * 20.0))
            vintage_boost = min(10.0, max(0.0, vintage_or_experience * 2.5))

            rate_mid = _parse_rate_midpoint(policy.get("interest_rate_range"), default=15.0 if loan_type == "PL" else 9.0)
            pricing_bonus = max(0.0, 12.0 - (rate_mid - (10.0 if loan_type == "PL" else 8.0)) * 1.5)

            score = min(97.0, 58.0 + min(18.0, cibil_headroom / 3.5) + income_boost + vintage_boost + pricing_bonus)
            score = round(score, 2)

            if score >= 82:
                probability = "high"
            elif score >= 68:
                probability = "medium"
            else:
                probability = "low"

            if loan_type == "PL":
                multiplier = 10 if score < 70 else 14 if score < 82 else 18
                ticket_max_lakh = min(50.0, max(2.0, (monthly_income * multiplier) / 100000.0))
                ticket_min_lakh = max(1.0, round(ticket_max_lakh * 0.25, 2))
            else:
                multiplier = 55 if score < 70 else 70 if score < 82 else 85
                ticket_max_lakh = min(500.0, max(10.0, (monthly_income * multiplier) / 100000.0))
                ticket_min_lakh = max(5.0, round(ticket_max_lakh * 0.35, 2))

            reason_parts = [
                f"CIBIL {cibil_score} meets {min_cibil}+",
                f"income fits lender threshold",
            ]
            if applicant_type == "self_employed" and min_vintage:
                reason_parts.append(f"vintage {vintage_or_experience}y meets {float(min_vintage)}y")

            passed.append({
                "lender_name": policy.get("lender_name"),
                "product_name": f"{_loan_label(loan_type)} • {applicant_type.replace('_', ' ').title()}",
                "score": score,
                "probability": probability,
                "expected_ticket_min": round(ticket_min_lakh, 2),
                "expected_ticket_max": round(ticket_max_lakh, 2),
                "key_reason": "; ".join(reason_parts),
                "policy_meta": {
                    "interest_rate_range": policy.get("interest_rate_range"),
                    "processing_fee": policy.get("processing_fee"),
                    "max_tenor_months": policy.get("max_tenor_months"),
                    "max_ltv": policy.get("max_ltv"),
                    "max_foir": policy.get("max_foir"),
                },
            })

        passed.sort(key=lambda item: item["score"], reverse=True)

        suggestions: List[str] = []
        if not passed:
            suggestions.append("Increase CIBIL score or add strong repayment history before re-checking.")
            suggestions.append("Provide higher verifiable monthly income/income proof.")
            if applicant_type == "self_employed":
                suggestions.append("Add business vintage and stronger cashflow proofs.")
        else:
            top = passed[:3]
            top_names = ", ".join(item["lender_name"] for item in top)
            suggestions.append(f"Start with {top_names} for fastest conversion.")
            suggestions.append("Keep bureau utilization low until disbursal decision.")

        return {
            "loan_type": loan_type,
            "loan_label": _loan_label(loan_type),
            "applicant_type": applicant_type,
            "total_evaluated": len(scoped_policies),
            "matches": passed,
            "rejection_reasons": rejection_reasons[:8],
            "suggested_actions": suggestions,
        }


def get_multi_loan_policy_service() -> MultiLoanPolicyService:
    base_dir = Path(__file__).resolve().parents[2]
    data_path = base_dir / "data" / "multi_loan_policy_2026.json"
    return MultiLoanPolicyService(data_path=data_path)
