"""Billing/subscription placeholders for monetization integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/razorpay/webhook")
async def razorpay_webhook_placeholder(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
):
    """Placeholder endpoint for Razorpay subscription webhooks.

    Signature validation and event persistence can be added once live Razorpay keys are provided.
    """
    payload: dict[str, Any] = await request.json()
    event = payload.get("event")
    logger.info(
        "Razorpay webhook received (placeholder): event=%s signature_present=%s",
        event,
        bool(x_razorpay_signature),
    )
    return {
        "status": "accepted",
        "event": event,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "note": "Webhook placeholder active. Signature verification not enabled yet.",
    }
