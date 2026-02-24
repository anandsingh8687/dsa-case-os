"""
WhatsApp API Endpoints

Per-case WhatsApp chat integration.
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query, Request
from fastapi.responses import PlainTextResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging

from app.services.whatsapp_service import (
    whatsapp_client,
    link_whatsapp_to_case,
    update_qr_generated_timestamp,
    save_whatsapp_message,
    get_case_chat_history
)
from app.services.whatsapp_cloud_service import whatsapp_cloud_service
from app.core.config import settings
from app.core.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class GenerateQRRequest(BaseModel):
    case_id: str


class GenerateQRResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    qr_code: Optional[str] = None  # Base64 data URL
    status: Optional[str] = None
    error: Optional[str] = None
    linked_number: Optional[str] = None  # Add this for already-linked check

    class Config:
        # Output camelCase for frontend JavaScript
        fields = {
            'session_id': 'sessionId',
            'qr_code': 'qrCode',
            'linked_number': 'linkedNumber'
        }
        populate_by_name = True


class SessionStatusResponse(BaseModel):
    session_id: str
    case_id: str
    status: str
    linked_number: Optional[str] = None
    has_qr_code: bool

    class Config:
        # Output camelCase for frontend JavaScript
        fields = {
            'session_id': 'sessionId',
            'case_id': 'caseId',
            'linked_number': 'linkedNumber',
            'has_qr_code': 'hasQrCode'
        }
        populate_by_name = True  # Allow both snake_case and camelCase input


class SendMessageRequest(BaseModel):
    case_id: str
    to: str  # Recipient number with country code
    message: str


class SendMessageResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    timestamp: Optional[int] = None
    error: Optional[str] = None


class WebhookMessageData(BaseModel):
    sessionId: str
    caseId: str
    messageId: str
    from_: str = None  # Renamed from 'from' since it's a Python keyword
    to: str
    body: str
    type: str
    timestamp: int
    hasMedia: bool

    class Config:
        fields = {'from_': 'from'}


class WhatsAppWebhook(BaseModel):
    event: str
    data: Dict[str, Any]


class ChatMessage(BaseModel):
    id: str
    message_id: str
    from_number: str = None  # Alias for 'from'
    to: str
    body: str
    type: str
    direction: str
    status: str
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None

    class Config:
        fields = {'from_number': 'from'}


class ChatHistoryResponse(BaseModel):
    case_id: str
    messages: List[ChatMessage]
    total: int


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/health")
async def whatsapp_health_check():
    """Check if WhatsApp service is running."""
    legacy_healthy = False
    if not settings.WHATSAPP_CLOUD_ONLY:
        legacy_healthy = await whatsapp_client.health_check()
    return {
        "status": "ok",
        "cloud_only_mode": settings.WHATSAPP_CLOUD_ONLY,
        "legacy_service_running": legacy_healthy,
        "cloud_api_configured": whatsapp_cloud_service.configured,
        "primary_number": "8130781881",
    }


@router.post("/generate-qr", response_model=GenerateQRResponse)
async def generate_qr_code(
    request: GenerateQRRequest,
    current_user: CurrentUser
):
    """
    Generate QR code for linking WhatsApp to a case.

    The QR code can be scanned with WhatsApp to link the user's WhatsApp
    to this specific case.
    """
    if settings.WHATSAPP_CLOUD_ONLY:
        raise HTTPException(
            status_code=410,
            detail="QR-based WhatsApp sessions are disabled. Use Meta Cloud API via 8130781881.",
        )

    logger.info(f"User {current_user.id} generating QR for case {request.case_id}")

    # TODO: Verify case belongs to current_user

    # Generate QR code via WhatsApp service
    result = await whatsapp_client.generate_qr_code(request.case_id)

    if result.get('success'):
        # Update database timestamp
        await update_qr_generated_timestamp(request.case_id)

        return GenerateQRResponse(
            success=True,
            session_id=result.get('sessionId'),
            qr_code=result.get('qrCode'),
            status=result.get('status'),
            linked_number=result.get('linkedNumber')  # Include linked number if already ready
        )
    else:
        return GenerateQRResponse(
            success=False,
            error=result.get('error', 'Failed to generate QR code')
        )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    current_user: CurrentUser
):
    """Get status of a WhatsApp session."""
    if settings.WHATSAPP_CLOUD_ONLY:
        raise HTTPException(
            status_code=410,
            detail="Session status is unavailable in cloud-only mode.",
        )

    result = await whatsapp_client.get_session_status(session_id)

    if 'error' in result:
        raise HTTPException(status_code=404, detail=result['error'])

    # Link WhatsApp number to case if status is 'ready' and not already linked
    if result.get('status') == 'ready' and result.get('linkedNumber'):
        await link_whatsapp_to_case(
            case_id=result['caseId'],
            whatsapp_number=result['linkedNumber'],
            session_id=session_id
        )

    # Transform camelCase keys from Node.js service to snake_case for FastAPI model
    return SessionStatusResponse(
        session_id=result.get('sessionId'),
        case_id=result.get('caseId'),
        status=result.get('status'),
        linked_number=result.get('linkedNumber'),
        has_qr_code=result.get('hasQrCode', False)
    )


@router.post("/send-message", response_model=SendMessageResponse)
async def send_whatsapp_message(
    request: SendMessageRequest,
    current_user: CurrentUser
):
    """
    Send a WhatsApp message for a case.

    Requires the case to have an active WhatsApp session.
    """
    from app.db.database import get_db_session

    if settings.WHATSAPP_CLOUD_ONLY:
        if not whatsapp_cloud_service.configured:
            raise HTTPException(status_code=503, detail="WhatsApp Cloud API is not configured")

        async with get_db_session() as db:
            row = await db.fetchrow(
                """
                SELECT case_id
                FROM cases
                WHERE case_id = $1
                  AND (organization_id = $2 OR user_id = $3)
                """,
                request.case_id,
                current_user.organization_id,
                current_user.id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Case not found")

        result = await whatsapp_cloud_service.send_text_message(request.to, request.message)
        if not result.get("success"):
            return SendMessageResponse(
                success=False,
                error=result.get("error", "Failed to send message"),
            )

        message_id = (((result.get("data") or {}).get("messages") or [{}])[0]).get("id")
        await save_whatsapp_message(
            case_id_str=request.case_id,
            message_id=message_id,
            from_number=settings.WHATSAPP_CLOUD_BUSINESS_NUMBER,
            to_number=request.to,
            message_body=request.message,
            direction='outbound',
            message_type='text',
            status='sent'
        )
        return SendMessageResponse(success=True, message_id=message_id)

    async with get_db_session() as db:
        query = """
            SELECT whatsapp_session_id, whatsapp_number
            FROM cases
            WHERE case_id = $1 AND user_id = $2
        """
        row = await db.fetchrow(query, request.case_id, current_user.id)

        if not row or not row['whatsapp_session_id']:
            raise HTTPException(
                status_code=400,
                detail="Case does not have an active WhatsApp session. Generate QR code first."
            )

        session_id = row['whatsapp_session_id']

    result = await whatsapp_client.send_message(
        session_id=session_id,
        to=request.to,
        message=request.message
    )

    if result.get('success'):
        # Save to database
        await save_whatsapp_message(
            case_id_str=request.case_id,
            message_id=result.get('messageId'),
            from_number=row['whatsapp_number'],  # From case's linked number
            to_number=request.to,
            message_body=request.message,
            direction='outbound',
            message_type='text',
            status='sent'
        )

        return SendMessageResponse(
            success=True,
            message_id=result.get('messageId'),
            timestamp=result.get('timestamp')
        )
    else:
        return SendMessageResponse(
            success=False,
            error=result.get('error', 'Failed to send message')
        )


@router.post("/cloud/send-message", response_model=SendMessageResponse)
async def send_whatsapp_cloud_message(
    request: SendMessageRequest,
    current_user: CurrentUser
):
    """Send message using Meta WhatsApp Cloud API (primary number 8130781881)."""
    if not whatsapp_cloud_service.configured:
        raise HTTPException(status_code=503, detail="WhatsApp Cloud API is not configured")

    from app.db.database import get_db_session

    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT case_id
            FROM cases
            WHERE case_id = $1
              AND (organization_id = $2 OR user_id = $3)
            """,
            request.case_id,
            current_user.organization_id,
            current_user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

    result = await whatsapp_cloud_service.send_text_message(request.to, request.message)
    if not result.get("success"):
        return SendMessageResponse(success=False, error=result.get("error", "Failed to send message"))

    message_id = (((result.get("data") or {}).get("messages") or [{}])[0]).get("id")
    await save_whatsapp_message(
        case_id_str=request.case_id,
        message_id=message_id,
        from_number=settings.WHATSAPP_CLOUD_BUSINESS_NUMBER,
        to_number=request.to,
        message_body=request.message,
        direction='outbound',
        message_type='text',
        status='sent'
    )

    return SendMessageResponse(
        success=True,
        message_id=message_id,
    )


@router.get("/chat-history/{case_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    case_id: str,
    current_user: CurrentUser,
    limit: int = 100
):
    """Get WhatsApp chat history for a case."""
    # TODO: Verify case belongs to current_user

    messages = await get_case_chat_history(case_id, limit)

    return ChatHistoryResponse(
        case_id=case_id,
        messages=messages,
        total=len(messages)
    )


@router.post("/disconnect/{case_id}")
async def disconnect_whatsapp(
    case_id: str,
    current_user: CurrentUser
):
    """Disconnect WhatsApp session for a case."""
    if settings.WHATSAPP_CLOUD_ONLY:
        raise HTTPException(
            status_code=410,
            detail="Session disconnect is unavailable in cloud-only mode.",
        )

    from app.db.database import get_db_session

    async with get_db_session() as db:
        query = """
            SELECT whatsapp_session_id
            FROM cases
            WHERE case_id = $1 AND user_id = $2
        """
        row = await db.fetchrow(query, case_id, current_user.id)

        if not row or not row['whatsapp_session_id']:
            raise HTTPException(status_code=400, detail="No active WhatsApp session")

        session_id = row['whatsapp_session_id']

    # Disconnect via WhatsApp service
    success = await whatsapp_client.disconnect_session(session_id)

    if success:
        # Clear session from database
        async with get_db_session() as db:
            query = """
                UPDATE cases
                SET whatsapp_session_id = NULL,
                    whatsapp_number = NULL,
                    updated_at = NOW()
                WHERE case_id = $1
            """
            await db.execute(query, case_id)

        return {"success": True, "message": "WhatsApp disconnected"}
    else:
        raise HTTPException(status_code=500, detail="Failed to disconnect WhatsApp")


# ============================================================
# WEBHOOK (for incoming messages from WhatsApp service)
# ============================================================

@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Webhook endpoint for WhatsApp service to send events.

    This is called by the Node.js WhatsApp service when messages are received.
    """
    payload = await request.json()

    # Meta WhatsApp Cloud API webhook shape.
    if payload.get("object") == "whatsapp_business_account":
        result = await whatsapp_cloud_service.handle_meta_webhook_payload(payload)
        return {"status": "received", "mode": "cloud", **result}

    # Legacy node webhook compatibility.
    webhook = WhatsAppWebhook(**payload)
    logger.info(f"Legacy webhook received: {webhook.event}")
    if webhook.event == 'message':
        data = webhook.data
        await save_whatsapp_message(
            case_id_str=data.get('caseId'),
            message_id=data.get('messageId'),
            from_number=data.get('from'),
            to_number=data.get('to'),
            message_body=data.get('body'),
            direction='inbound',
            message_type=data.get('type', 'text'),
            status='received'
        )
        logger.info(f"Incoming WhatsApp message saved for case {data.get('caseId')}")
    return {"status": "received", "mode": "legacy"}


@router.get("/webhook")
async def whatsapp_cloud_webhook_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Meta Cloud API webhook verification endpoint."""
    ok, response = await whatsapp_cloud_service.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if not ok:
        raise HTTPException(status_code=403, detail=response)
    return PlainTextResponse(response)
