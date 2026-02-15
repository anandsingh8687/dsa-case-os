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
        f"Based on this profile, {payload['matches_found']} lenders are immediately matchable for Business Loan. "
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
                        f"CIBIL {payload['cibil_score']}, monthly turnover ₹{payload['monthly_turnover_rupees']:,}, "
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


@router.post("", response_model=QuickScanResponse)
async def run_quick_scan(request: QuickScanRequest, current_user: CurrentUser):
    """Run instant BL quick scan against current lender rule base."""
    if request.loan_type != "BL":
        raise HTTPException(
            status_code=400,
            detail="Quick Scan currently supports BL. PL/HL/LAP will be enabled after multi-loan knowledge base import.",
        )

    if not request.pincode.isdigit():
        raise HTTPException(status_code=400, detail="Pincode must be a 6-digit numeric value")

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

    eligibility = await score_case_eligibility(borrower=borrower, program_type="banking")
    passed = [r for r in eligibility.results if r.hard_filter_status.value == "pass"]
    top_matches_raw = passed[:10]
    top_matches = [_serialize_match(item) for item in top_matches_raw]

    top_ticket = max(
        (m.expected_ticket_max or 0 for m in top_matches),
        default=0,
    )
    top_ticket_label = f"₹{top_ticket:.1f}L" if top_ticket > 0 else "policy-based"
    top_lenders_label = ", ".join([m.lender_name for m in top_matches[:3]]) if top_matches else "none yet"

    payload = {
        "matches_found": len(top_matches),
        "cibil_score": request.cibil_score,
        "monthly_turnover_rupees": int(monthly_turnover_lakhs * 100000),
        "vintage_years": request.vintage_or_experience,
        "pincode": request.pincode,
        "top_lenders_label": top_lenders_label,
        "top_ticket_label": top_ticket_label,
    }
    pitch = await _generate_pitch_summary(payload)

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

    scan_record = {
        "request": request.model_dump(),
        "response": {
            "loan_type": request.loan_type,
            "matches_found": len(top_matches),
            "total_evaluated": eligibility.total_lenders_evaluated,
            "top_matches": [m.model_dump() for m in top_matches],
            "summary_pitch": pitch,
            "insights": insights,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    async with get_db_session() as db:
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
        total_evaluated=eligibility.total_lenders_evaluated,
        top_matches=top_matches,
        summary_pitch=pitch,
        insights=insights,
    )


@router.get("/{scan_id}", response_model=QuickScanResponse)
async def get_quick_scan(scan_id: UUID, current_user: CurrentUser):
    """Fetch a previously generated quick scan owned by current user."""
    async with get_db_session() as db:
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
