"""Meta WhatsApp Cloud API integration for inbound forwarding and command workflows."""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, text

from app.core.config import settings
from app.core.enums import CaseStatus, DocumentStatus
from app.db.database import async_session_maker
from app.models.case import Case, Document, DocumentProcessingJob
from app.models.user import User
from app.schemas.shared import CaseCreate
from app.services.file_storage import compute_file_hash, get_storage_backend
from app.services.rq_queue import enqueue_document_job
from app.services.stages.stage0_case_entry import CaseEntryService
from app.services.stages.stage7_copilot import query_copilot

logger = logging.getLogger(__name__)

CASE_ID_RE = re.compile(r"\bCASE-\d{8}-\d{4}\b", re.IGNORECASE)
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)


class WhatsAppCloudService:
    """Wrapper around Meta Graph API for WhatsApp Cloud API."""

    def __init__(self) -> None:
        self.api_version = settings.WHATSAPP_CLOUD_API_VERSION
        self.access_token = settings.WHATSAPP_CLOUD_ACCESS_TOKEN
        self.phone_number_id = settings.WHATSAPP_CLOUD_PHONE_NUMBER_ID
        self.verify_token = settings.WHATSAPP_CLOUD_VERIFY_TOKEN
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.timeout = 40.0

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    async def verify_webhook(self, mode: str, verify_token: str, challenge: str) -> tuple[bool, str]:
        if mode == "subscribe" and verify_token == self.verify_token:
            return True, challenge
        return False, "Invalid verification token"

    async def send_text_message(self, to_number: str, body: str, phone_number_id: str | None = None) -> dict[str, Any]:
        if not self.configured:
            return {"success": False, "error": "WhatsApp Cloud API not configured"}

        endpoint = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": normalize_phone(to_number),
            "type": "text",
            "text": {"preview_url": False, "body": body[:4000]},
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.error("WhatsApp send failed: %s %s", response.status_code, response.text)
                return {"success": False, "status_code": response.status_code, "error": response.text}
            data = response.json()
            return {"success": True, "data": data}
        except Exception as exc:  # noqa: BLE001
            logger.error("WhatsApp send error: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _get_media_metadata(self, media_id: str) -> dict[str, Any] | None:
        if not self.configured:
            return None
        endpoint = f"{self.base_url}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(endpoint, headers=headers)
        if response.status_code >= 400:
            logger.error("Meta media metadata fetch failed: %s %s", response.status_code, response.text)
            return None
        return response.json()

    async def _download_media(self, media_url: str) -> bytes | None:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(media_url, headers=headers)
        if response.status_code >= 400:
            logger.error("Meta media download failed: %s %s", response.status_code, response.text)
            return None
        return response.content

    async def handle_meta_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        processed = 0
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for message in messages:
                    try:
                        await self._handle_single_message(value, message)
                        processed += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed processing webhook message: %s", exc, exc_info=True)
        return {"processed": processed}

    async def _handle_single_message(self, value: dict[str, Any], message: dict[str, Any]) -> None:
        from_number = normalize_phone(message.get("from", ""))
        contacts = value.get("contacts") or []
        profile_name = ""
        if contacts:
            profile_name = (contacts[0].get("profile") or {}).get("name") or ""

        body_text = extract_message_text(message)
        media_type = detect_media_type(message)
        media_meta = message.get(media_type) if media_type else None

        user = await self._find_registered_user(from_number)
        if user:
            await self._handle_dsa_message(user, from_number, profile_name, body_text, media_type, media_meta)
        else:
            await self._handle_public_message(from_number, body_text)

    async def _find_registered_user(self, phone_number: str) -> User | None:
        normalized = normalize_phone(phone_number)
        last10 = normalized[-10:] if len(normalized) >= 10 else normalized
        async with async_session_maker() as db:
            row = await db.execute(select(User).where(User.phone.isnot(None)))
            users = row.scalars().all()
            for user in users:
                user_phone = normalize_phone(user.phone or "")
                if not user_phone:
                    continue
                if user_phone == normalized or user_phone.endswith(last10):
                    return user
        return None

    async def _handle_public_message(self, from_number: str, body_text: str) -> None:
        query = (body_text or "").strip() or "How can you help with business loans?"
        try:
            reply = await query_copilot(query=query, user_id=None, organization_id=None, ui_history=None)
            text_response = (reply.answer or "").strip()[:1400]
        except Exception:
            text_response = (
                "Hi. I can help with business loan eligibility, documents, CIBIL improvement, EMI guidance, and lender options. "
                "Share your loan need, turnover, and pincode to start."
            )
        await self.send_text_message(from_number, text_response)

    async def _handle_dsa_message(
        self,
        user: User,
        from_number: str,
        profile_name: str,
        body_text: str,
        media_type: str | None,
        media_meta: dict[str, Any] | None,
    ) -> None:
        text_lower = (body_text or "").strip().lower()

        if text_lower.startswith("/newcase"):
            case = await self._create_case_for_user(user, profile_name or "WhatsApp Prospect")
            await self.send_text_message(
                from_number,
                f"New case created: {case.case_id}. Forward documents now and I will process automatically.",
            )
            return

        hinted_case = await self._resolve_case_for_message(user, body_text or "", profile_name)

        if text_lower.startswith("/status"):
            if hinted_case:
                await self.send_text_message(
                    from_number,
                    f"{hinted_case.case_id} status: {hinted_case.status}, completeness: {hinted_case.completeness_score or 0:.0f}%",
                )
            else:
                await self.send_text_message(from_number, "Case not found. Share case id like /status CASE-YYYYMMDD-0001")
            return

        if text_lower.startswith("/report"):
            if hinted_case:
                summary = await self._build_report_summary(hinted_case.case_id)
                await self.send_text_message(from_number, summary)
            else:
                await self.send_text_message(from_number, "Case not found for report command. Please include case id.")
            return

        if text_lower.startswith("/update"):
            if hinted_case:
                await self.send_text_message(from_number, f"Update mode active for {hinted_case.case_id}. Forward docs/files now.")
            else:
                await self.send_text_message(from_number, "Please include case id after /update. Example: /update CASE-20260223-0001")
            return

        case = hinted_case or await self._create_case_for_user(user, profile_name or "WhatsApp Prospect")

        if media_type and media_meta:
            attached = await self._attach_media_to_case(case, media_type, media_meta)
            if attached:
                await self.send_text_message(
                    from_number,
                    f"Received {media_type} for {case.case_id}. Processing has started. Use /status {case.case_id}.",
                )
            else:
                await self.send_text_message(from_number, "I could not download that media file. Please resend.")
            return

        # Non-command text: treat as copilot query with org context.
        if body_text and body_text.strip():
            reply = await query_copilot(
                query=body_text,
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
                ui_history=None,
            )
            await self.send_text_message(from_number, (reply.answer or "").strip()[:1400])
            return

        await self.send_text_message(from_number, "Use /newcase, /status, /report or forward documents to start processing.")

    async def _resolve_case_for_message(self, user: User, body_text: str, profile_name: str) -> Case | None:
        async with async_session_maker() as db:
            case_id_match = CASE_ID_RE.search(body_text or "")
            if case_id_match:
                case_id = case_id_match.group(0).upper()
                row = await db.execute(
                    select(Case).where(
                        Case.case_id == case_id,
                        Case.organization_id == user.organization_id,
                    )
                )
                case = row.scalar_one_or_none()
                if case:
                    return case

            pan_match = PAN_RE.search((body_text or "").upper())
            if pan_match:
                pan = pan_match.group(0)
                row = await db.execute(
                    text(
                        """
                        SELECT c.id
                        FROM cases c
                        INNER JOIN borrower_features bf ON bf.case_id = c.id
                        WHERE UPPER(bf.pan_number) = :pan
                          AND c.organization_id = :organization_id
                        ORDER BY c.updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"pan": pan, "organization_id": user.organization_id},
                )
                mapping = row.mappings().first()
                if mapping and mapping.get("id"):
                    case = await db.get(Case, mapping["id"])
                    if case:
                        return case

            if profile_name:
                row = await db.execute(
                    select(Case)
                    .where(
                        Case.organization_id == user.organization_id,
                        Case.borrower_name.ilike(f"%{profile_name}%"),
                    )
                    .order_by(Case.updated_at.desc())
                )
                case = row.scalars().first()
                if case:
                    return case

            row = await db.execute(
                select(Case)
                .where(Case.organization_id == user.organization_id)
                .order_by(Case.updated_at.desc())
            )
            return row.scalars().first()

    async def _create_case_for_user(self, user: User, borrower_name: str) -> Case:
        async with async_session_maker() as db:
            service = CaseEntryService(db)
            response = await service.create_case(
                user,
                CaseCreate(
                    borrower_name=(borrower_name or "WhatsApp Prospect")[:255],
                    entity_type=None,
                    program_type=None,
                ),
            )
            row = await db.execute(select(Case).where(Case.case_id == response.case_id))
            case = row.scalar_one()
            return case

    async def _attach_media_to_case(self, case: Case, media_type: str, media_meta: dict[str, Any]) -> bool:
        media_id = media_meta.get("id")
        if not media_id:
            return False

        metadata = await self._get_media_metadata(media_id)
        if not metadata:
            return False

        media_url = metadata.get("url")
        mime_type = metadata.get("mime_type") or media_meta.get("mime_type") or "application/octet-stream"
        if not media_url:
            return False

        file_bytes = await self._download_media(media_url)
        if not file_bytes:
            return False

        filename = media_meta.get("filename") or f"{media_id}{mimetypes.guess_extension(mime_type) or '.bin'}"
        storage = get_storage_backend()

        file_stream = io.BytesIO(file_bytes)
        file_hash = compute_file_hash(file_stream)
        storage_key = await storage.store_file(file_stream, case.case_id, filename)

        async with async_session_maker() as db:
            case_row = await db.get(Case, case.id)
            if not case_row:
                return False

            doc = Document(
                case_id=case_row.id,
                organization_id=case_row.organization_id,
                original_filename=filename,
                storage_key=storage_key,
                file_size_bytes=len(file_bytes),
                mime_type=mime_type,
                file_hash=file_hash,
                doc_type="unknown",
                status=DocumentStatus.UPLOADED.value,
            )
            db.add(doc)
            await db.flush()

            job = DocumentProcessingJob(
                case_id=case_row.id,
                document_id=doc.id,
                organization_id=case_row.organization_id,
                status="queued",
                attempts=0,
                max_attempts=settings.DOC_QUEUE_MAX_ATTEMPTS,
            )
            db.add(job)
            case_row.status = CaseStatus.PROCESSING.value
            await db.commit()

            if settings.RQ_ASYNC_ENABLED:
                try:
                    enqueue_document_job(str(job.id))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to enqueue WhatsApp media processing: %s", exc, exc_info=True)

        return True

    async def _build_report_summary(self, case_id: str) -> str:
        async with async_session_maker() as db:
            row = await db.execute(
                text(
                    """
                    SELECT c.case_id, c.status, c.borrower_name, c.completeness_score,
                           cr.generated_at
                    FROM cases c
                    LEFT JOIN case_reports cr ON cr.case_id = c.id
                    WHERE c.case_id = :case_id
                    ORDER BY cr.generated_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            )
            result = row.mappings().first()

        if not result:
            return f"Case {case_id} not found."

        return (
            f"Case {result['case_id']} ({result.get('borrower_name') or 'Borrower'}) is {result['status']} "
            f"with {float(result.get('completeness_score') or 0):.0f}% completeness. "
            "Use dashboard for full lender-wise details."
        )


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("91") and len(digits) > 10:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def extract_message_text(message: dict[str, Any]) -> str:
    if message.get("type") == "text":
        return ((message.get("text") or {}).get("body") or "").strip()
    return ""


def detect_media_type(message: dict[str, Any]) -> str | None:
    msg_type = (message.get("type") or "").strip().lower()
    if msg_type in {"document", "image", "audio", "video"}:
        return msg_type
    return None


whatsapp_cloud_service = WhatsAppCloudService()
