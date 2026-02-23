"""Quick Scan endpoints for instant business loan eligibility preview."""

import io
import json
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentUser
from app.schemas.shared import BorrowerFeatureVector, EligibilityResult
from app.services.stages.stage4_eligibility import score_case_eligibility
from app.db.database import get_db_session
from app.services.multi_loan_policy_service import get_multi_loan_policy_service


router = APIRouter(prefix="/quick-scan", tags=["quick_scan"])


class QuickScanRequest(BaseModel):
    loan_type: Literal["BL", "PL", "HL", "LAP"] = "BL"
    cibil_score: int = Field(..., ge=300, le=900)
    monthly_income_or_turnover: float = Field(..., gt=0)
    vintage_or_experience: float = Field(..., ge=0)
    entity_type_or_employer: str = Field(..., min_length=2)
    pincode: str = Field(..., min_length=6, max_length=6)


class QuickScanMatch(BaseModel):
    lender_name: str
    product_name: str
    score: float
    probability: Optional[str] = None
    expected_ticket_min: Optional[float] = None
    expected_ticket_max: Optional[float] = None
    key_reason: Optional[str] = None


class QuickScanResponse(BaseModel):
    scan_id: str
    loan_type: str
    matches_found: int
    total_evaluated: int
    top_matches: List[QuickScanMatch]
    summary_pitch: str
    insights: Dict[str, Any]


def _infer_entity(entity_value: str) -> str:
    normalized = entity_value.strip().lower().replace(" ", "_")
    mapping = {
        "proprietorship": "proprietorship",
        "partnership": "partnership",
        "llp": "llp",
        "pvt_ltd": "pvt_ltd",
        "private_limited": "pvt_ltd",
        "public_limited": "public_ltd",
        "public_ltd": "public_ltd",
        "trust": "trust",
        "society": "society",
        "huf": "huf",
    }
    return mapping.get(normalized, "proprietorship")


def _serialize_match(result: EligibilityResult) -> QuickScanMatch:
    details = result.hard_filter_details or {}
    key_reason = None
    if isinstance(details, dict):
        matched_signals = details.get("matched_signals")
        if isinstance(matched_signals, list) and matched_signals:
            key_reason = str(matched_signals[1] if len(matched_signals) > 1 else matched_signals[0])
        elif isinstance(details.get("score_breakdown"), list) and details["score_breakdown"]:
            top_component = details["score_breakdown"][0]
            component_label = top_component.get("label") or top_component.get("component")
            component_score = top_component.get("score")
            if component_label and component_score is not None:
                key_reason = f"Strong {component_label}: {round(float(component_score))}/100"
        elif result.eligibility_score is not None:
            key_reason = f"Composite score {round(float(result.eligibility_score))}/100 with hard filters passed"

    return QuickScanMatch(
        lender_name=result.lender_name,
        product_name=result.product_name,
        score=float(result.eligibility_score or 0.0),
        probability=result.approval_probability.value if result.approval_probability else None,
        expected_ticket_min=result.expected_ticket_min,
        expected_ticket_max=result.expected_ticket_max,
        key_reason=key_reason,
    )


async def _generate_pitch_summary(payload: Dict[str, Any]) -> str:
    """Generate a short 2-line DSA pitch with LLM fallback to deterministic text."""
    fallback = (
        f"Based on this profile, {payload['matches_found']} lenders are immediately matchable for {payload['loan_label']}. "
        f"Top ticket potential is up to {payload['top_ticket_label']} with strongest fit in {payload['top_lenders_label']}."
    )

    if not settings.LLM_API_KEY:
        return fallback

    try:
        client = AsyncOpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=1.0,
            max_tokens=120,
            messages=[
                {
                    "role": "system",
                    "content": "You are a loan advisor. Write exactly 2 concise lines in professional Hinglish-friendly English for a DSA to read to customer.",
                },
                {
                    "role": "user",
                    "content": (
                        "Generate a 2-line pitch for this quick scan: "
                        f"Loan type {payload['loan_label']}, CIBIL {payload['cibil_score']}, monthly input ₹{payload['monthly_turnover_rupees']:,}, "
                        f"vintage {payload['vintage_years']} years, pincode {payload['pincode']}, "
                        f"matches {payload['matches_found']} lenders, top lenders {payload['top_lenders_label']}, "
                        f"max ticket approx {payload['top_ticket_label']}."
                    ),
                },
            ],
            timeout=10,
        )
        text = (response.choices[0].message.content or "").strip()
        return text if text else fallback
    except Exception:
        return fallback


def _decode_scan_data(raw_value: Any) -> Dict[str, Any]:
    """Normalize quick scan payload from JSONB driver return types."""
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _is_missing_org_column_error(error: Exception) -> bool:
    return "organization_id" in str(error).lower() and (
        "column" in str(error).lower() or "does not exist" in str(error).lower()
    )


@router.post("", response_model=QuickScanResponse)
async def run_quick_scan(request: QuickScanRequest, current_user: CurrentUser):
    """Run instant BL/PL/HL quick scan against available lender rules."""
    if not request.pincode.isdigit():
        raise HTTPException(status_code=400, detail="Pincode must be a 6-digit numeric value")
    loan_label = {
        "BL": "Business Loan",
        "PL": "Personal Loan",
        "HL": "Home Loan",
        "LAP": "Loan Against Property",
    }.get(request.loan_type, request.loan_type)

    eligibility = None
    insights: Dict[str, Any] = {}
    top_matches: List[QuickScanMatch] = []
    total_evaluated = 0

    if request.loan_type == "BL":
        monthly_turnover_lakhs = float(request.monthly_income_or_turnover)
        annual_turnover_lakhs = round(monthly_turnover_lakhs * 12.0, 2)

        borrower = BorrowerFeatureVector(
            entity_type=_infer_entity(request.entity_type_or_employer),
            business_vintage_years=request.vintage_or_experience,
            pincode=request.pincode,
            cibil_score=request.cibil_score,
            annual_turnover=annual_turnover_lakhs,
            monthly_turnover=round(monthly_turnover_lakhs * 100000, 2),
            monthly_credit_avg=round(monthly_turnover_lakhs * 100000, 2),
            feature_completeness=78.0,
        )

        # Evaluate across the full active lender pool so quick scan is not restricted
        # to only one program bucket.
        eligibility = await score_case_eligibility(borrower=borrower, program_type=None)
        passed = [r for r in eligibility.results if r.hard_filter_status.value == "pass"]
        top_matches_raw = passed[:10]
        top_matches = [_serialize_match(item) for item in top_matches_raw]
        total_evaluated = eligibility.total_lenders_evaluated

        avg_score = round(sum((m.score for m in top_matches), 2) / len(top_matches), 2) if top_matches else 0.0
        median_score = round(median([m.score for m in top_matches]), 2) if top_matches else 0.0

        insights = {
            "avg_score": avg_score,
            "median_score": median_score,
            "rejection_reasons": eligibility.rejection_reasons,
            "suggested_actions": eligibility.suggested_actions,
            "dynamic_recommendations": eligibility.dynamic_recommendations[:3],
            "assumptions": {
                "turnover_unit": "input interpreted as monthly turnover in Lakhs",
                "loan_type_scope": "business_loan_only",
            },
        }
    elif request.loan_type in {"PL", "HL"}:
        policy_service = get_multi_loan_policy_service()
        result = policy_service.evaluate(
            loan_type=request.loan_type,
            cibil_score=request.cibil_score,
            monthly_income_or_turnover=float(request.monthly_income_or_turnover),
            vintage_or_experience=float(request.vintage_or_experience),
            entity_type_or_employer=request.entity_type_or_employer,
        )

        total_evaluated = int(result.get("total_evaluated") or 0)
        raw_matches = result.get("matches") or []
        top_matches = [
            QuickScanMatch(
                lender_name=item.get("lender_name", "Unknown Lender"),
                product_name=item.get("product_name", loan_label),
                score=float(item.get("score") or 0.0),
                probability=item.get("probability"),
                expected_ticket_min=item.get("expected_ticket_min"),
                expected_ticket_max=item.get("expected_ticket_max"),
                key_reason=item.get("key_reason"),
            )
            for item in raw_matches[:10]
        ]

        avg_score = round(sum((m.score for m in top_matches), 2) / len(top_matches), 2) if top_matches else 0.0
        median_score = round(median([m.score for m in top_matches]), 2) if top_matches else 0.0
        insights = {
            "avg_score": avg_score,
            "median_score": median_score,
            "rejection_reasons": result.get("rejection_reasons", []),
            "suggested_actions": result.get("suggested_actions", []),
            "dynamic_recommendations": [],
            "assumptions": {
                "income_unit": "PL/HL input interpreted as monthly income in INR (values <1000 treated as Lakhs)",
                "knowledge_base": "multi_loan_policy_2026.json",
                "applicant_type": result.get("applicant_type"),
            },
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Quick Scan does not support {request.loan_type} yet.",
        )

    top_ticket = max(
        (m.expected_ticket_max or 0 for m in top_matches),
        default=0,
    )
    top_ticket_label = f"₹{top_ticket:.1f}L" if top_ticket > 0 else "policy-based"
    top_lenders_label = ", ".join([m.lender_name for m in top_matches[:3]]) if top_matches else "none yet"

    payload = {
        "loan_label": loan_label,
        "matches_found": len(top_matches),
        "cibil_score": request.cibil_score,
        "monthly_turnover_rupees": (
            int(float(request.monthly_income_or_turnover) * 100000)
            if request.loan_type == "BL"
            else int(float(request.monthly_income_or_turnover) * 100000)
            if float(request.monthly_income_or_turnover) < 1000
            else int(float(request.monthly_income_or_turnover))
        ),
        "vintage_years": request.vintage_or_experience,
        "pincode": request.pincode,
        "top_lenders_label": top_lenders_label,
        "top_ticket_label": top_ticket_label,
    }
    pitch = await _generate_pitch_summary(payload)

    scan_record = {
        "request": request.model_dump(),
        "response": {
            "loan_type": request.loan_type,
            "matches_found": len(top_matches),
            "total_evaluated": total_evaluated,
            "top_matches": [m.model_dump() for m in top_matches],
            "summary_pitch": pitch,
            "insights": insights,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    user_org_id = getattr(current_user, "organization_id", None)

    async with get_db_session() as db:
        try:
            scan_id = await db.fetchval(
                """
                INSERT INTO quick_scans (user_id, organization_id, loan_type, pincode, scan_data)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING id::text
                """,
                current_user.id,
                user_org_id,
                request.loan_type,
                request.pincode,
                json.dumps(scan_record),
            )
        except Exception as error:
            if not _is_missing_org_column_error(error):
                raise
            scan_id = await db.fetchval(
                """
                INSERT INTO quick_scans (user_id, loan_type, pincode, scan_data)
                VALUES ($1, $2, $3, $4::jsonb)
                RETURNING id::text
                """,
                current_user.id,
                request.loan_type,
                request.pincode,
                json.dumps(scan_record),
            )

    return QuickScanResponse(
        scan_id=scan_id,
        loan_type=request.loan_type,
        matches_found=len(top_matches),
        total_evaluated=total_evaluated,
        top_matches=top_matches,
        summary_pitch=pitch,
        insights=insights,
    )


@router.get("/knowledge-base/stats")
async def get_quick_scan_knowledge_base_stats(current_user: CurrentUser):
    """Expose quick-scan PL/HL dataset coverage for admin and smoke checks."""
    policy_service = get_multi_loan_policy_service()
    return policy_service.stats()


@router.get("/{scan_id}", response_model=QuickScanResponse)
async def get_quick_scan(scan_id: UUID, current_user: CurrentUser):
    """Fetch a previously generated quick scan owned by current user."""
    async with get_db_session() as db:
        if current_user.role == "super_admin":
            row = await db.fetchrow(
                "SELECT scan_data FROM quick_scans WHERE id = $1",
                scan_id,
            )
        elif getattr(current_user, "organization_id", None):
            try:
                row = await db.fetchrow(
                    """
                    SELECT scan_data
                    FROM quick_scans
                    WHERE id = $1 AND organization_id = $2
                    """,
                    scan_id,
                    getattr(current_user, "organization_id", None),
                )
            except Exception as error:
                if not _is_missing_org_column_error(error):
                    raise
                row = await db.fetchrow(
                    """
                    SELECT scan_data
                    FROM quick_scans
                    WHERE id = $1 AND user_id = $2
                    """,
                    scan_id,
                    current_user.id,
                )
        else:
            row = await db.fetchrow(
                """
                SELECT scan_data
                FROM quick_scans
                WHERE id = $1 AND user_id = $2
                """,
                scan_id,
                current_user.id,
            )

    if not row:
        raise HTTPException(status_code=404, detail="Quick scan not found")

    payload = _decode_scan_data(row["scan_data"])
    response = payload.get("response") or {}
    response["scan_id"] = str(scan_id)
    return QuickScanResponse(**response)


@router.get("/{scan_id}/card")
async def get_quick_scan_card(scan_id: UUID, current_user: CurrentUser):
    """Generate a simple shareable PNG result card for a quick scan."""
    async with get_db_session() as db:
        if current_user.role == "super_admin":
            row = await db.fetchrow("SELECT scan_data FROM quick_scans WHERE id = $1", scan_id)
        elif getattr(current_user, "organization_id", None):
            try:
                row = await db.fetchrow(
                    """
                    SELECT scan_data
                    FROM quick_scans
                    WHERE id = $1 AND organization_id = $2
                    """,
                    scan_id,
                    getattr(current_user, "organization_id", None),
                )
            except Exception as error:
                if not _is_missing_org_column_error(error):
                    raise
                row = await db.fetchrow(
                    """
                    SELECT scan_data
                    FROM quick_scans
                    WHERE id = $1 AND user_id = $2
                    """,
                    scan_id,
                    current_user.id,
                )
        else:
            row = await db.fetchrow(
                """
                SELECT scan_data
                FROM quick_scans
                WHERE id = $1 AND user_id = $2
                """,
                scan_id,
                current_user.id,
            )

    if not row:
        raise HTTPException(status_code=404, detail="Quick scan not found")

    payload = _decode_scan_data(row["scan_data"])
    response = payload.get("response") or {}

    width, height = 1200, 675
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.rectangle([(0, 0), (width, 90)], fill=(21, 58, 163))
    draw.text((40, 30), "Credilo Eligibility Quick Scan", fill="white", font=title_font)
    draw.text((860, 30), datetime.now(timezone.utc).strftime("%d %b %Y"), fill="white", font=body_font)

    draw.text((40, 120), f"Scan ID: {scan_id}", fill=(31, 41, 55), font=body_font)
    draw.text((40, 150), f"Loan Type: {response.get('loan_type', 'BL')}", fill=(31, 41, 55), font=body_font)
    draw.text((40, 180), f"Matches: {response.get('matches_found', 0)} / {response.get('total_evaluated', 0)}", fill=(31, 41, 55), font=body_font)

    draw.text((40, 230), "Top Lenders", fill=(17, 24, 39), font=title_font)

    top_matches: List[Dict[str, Any]] = response.get("top_matches") or []
    y = 270
    for idx, match in enumerate(top_matches[:5], start=1):
        lender = match.get("lender_name", "Unknown")
        score = match.get("score", 0)
        ticket = match.get("expected_ticket_max")
        ticket_text = f"₹{ticket:.1f}L" if isinstance(ticket, (int, float)) else "N/A"
        line = f"#{idx}  {lender}  | Score {round(float(score), 1)}  | Max Ticket {ticket_text}"
        draw.text((40, y), line, fill=(55, 65, 81), font=body_font)
        y += 42

    draw.rectangle([(40, 520), (1160, 635)], outline=(209, 213, 219), width=1)
    summary = response.get("summary_pitch", "")
    draw.text((55, 545), "Pitch Summary:", fill=(17, 24, 39), font=title_font)
    draw.text((55, 575), summary[:180], fill=(75, 85, 99), font=body_font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")
