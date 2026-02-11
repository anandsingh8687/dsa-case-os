"""
WhatsApp Service Client

Communicates with the Node.js WhatsApp service for per-case chat integration.
"""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime as dt
import logging

from app.core.config import settings
from app.db.database import get_db_session

logger = logging.getLogger(__name__)


class WhatsAppServiceClient:
    """Client for WhatsApp microservice."""

    def __init__(self):
        self.base_url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://localhost:3001')
        self.timeout = 30.0

    async def health_check(self) -> bool:
        """Check if WhatsApp service is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"WhatsApp service health check failed: {e}")
            return False

    async def generate_qr_code(self, case_id: str) -> Dict[str, Any]:
        """
        Generate QR code for linking WhatsApp to a case.

        Args:
            case_id: Case ID to link

        Returns:
            {
                'success': bool,
                'session_id': str,
                'qr_code': str (base64 data URL),
                'status': str
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/generate-qr",
                    json={'caseId': case_id},
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"QR code generated for case {case_id}: session {data.get('sessionId')}")
                    return data
                else:
                    error_data = response.json()
                    logger.error(f"Failed to generate QR code: {error_data}")
                    return {
                        'success': False,
                        'error': error_data.get('error', 'Unknown error')
                    }

        except Exception as e:
            logger.error(f"Error generating QR code for case {case_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of a WhatsApp session.

        Args:
            session_id: Session ID

        Returns:
            {
                'sessionId': str,
                'caseId': str,
                'status': str,
                'linkedNumber': str or None,
                'hasQrCode': bool
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/session/{session_id}",
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {
                        'error': f'Session not found or error: {response.status_code}'
                    }

        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            return {'error': str(e)}

    async def send_message(
        self,
        session_id: str,
        to: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp message.

        Args:
            session_id: Session ID
            to: Recipient number (with country code, e.g., 919876543210)
            message: Message text

        Returns:
            {
                'success': bool,
                'messageId': str,
                'timestamp': int
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/send-message",
                    json={
                        'sessionId': session_id,
                        'to': to,
                        'message': message
                    },
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Message sent via session {session_id} to {to}")
                    return data
                else:
                    error_data = response.json()
                    logger.error(f"Failed to send message: {error_data}")
                    return {
                        'success': False,
                        'error': error_data.get('error', 'Unknown error')
                    }

        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def disconnect_session(self, session_id: str) -> bool:
        """
        Disconnect a WhatsApp session.

        Args:
            session_id: Session ID

        Returns:
            Success boolean
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/disconnect",
                    json={'sessionId': session_id},
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    logger.info(f"Session {session_id} disconnected")
                    return True
                else:
                    logger.error(f"Failed to disconnect session: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Error disconnecting session: {e}")
            return False

    async def get_qr_code(self, session_id: str) -> Optional[str]:
        """
        Get QR code data URL for a session.

        Args:
            session_id: Session ID

        Returns:
            Base64 data URL of QR code or None
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/qr-code/{session_id}",
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('qrCode')
                else:
                    return None

        except Exception as e:
            logger.error(f"Error getting QR code: {e}")
            return None


# ============================================================
# DATABASE OPERATIONS
# ============================================================

async def link_whatsapp_to_case(
    case_id: str,
    whatsapp_number: str,
    session_id: str
) -> bool:
    """
    Link a WhatsApp number to a case in the database.

    Args:
        case_id: Case ID
        whatsapp_number: WhatsApp number (with country code)
        session_id: Session ID from WhatsApp service

    Returns:
        Success boolean
    """
    try:
        async with get_db_session() as db:
            query = """
                UPDATE cases
                SET whatsapp_number = $1,
                    whatsapp_session_id = $2,
                    whatsapp_linked_at = NOW(),
                    updated_at = NOW()
                WHERE case_id = $3
            """

            await db.execute(query, whatsapp_number, session_id, case_id)
            logger.info(f"WhatsApp {whatsapp_number} linked to case {case_id}")
            return True

    except Exception as e:
        logger.error(f"Error linking WhatsApp to case: {e}")
        return False


async def update_qr_generated_timestamp(case_id: str) -> bool:
    """Update the QR generated timestamp for a case."""
    try:
        async with get_db_session() as db:
            query = """
                UPDATE cases
                SET whatsapp_qr_generated_at = NOW(),
                    updated_at = NOW()
                WHERE case_id = $1
            """

            await db.execute(query, case_id)
            return True

    except Exception as e:
        logger.error(f"Error updating QR timestamp: {e}")
        return False


async def save_whatsapp_message(
    case_id_str: str,
    message_id: str,
    from_number: str,
    to_number: str,
    message_body: str,
    direction: str,  # 'inbound' or 'outbound'
    message_type: str = 'text',
    status: str = 'sent'
) -> bool:
    """
    Save a WhatsApp message to the database.

    Args:
        case_id_str: Case ID
        message_id: WhatsApp message ID
        from_number: Sender number
        to_number: Recipient number
        message_body: Message text
        direction: 'inbound' or 'outbound'
        message_type: Message type (text, image, etc.)
        status: Message status

    Returns:
        Success boolean
    """
    try:
        async with get_db_session() as db:
            # Get case UUID from case_id string
            case_query = "SELECT id FROM cases WHERE case_id = $1"
            row = await db.fetchrow(case_query, case_id_str)

            if not row:
                logger.error(f"Case not found: {case_id_str}")
                return False

            case_uuid = row['id']

            # Insert message
            query = """
                INSERT INTO whatsapp_messages (
                    case_id, message_id, from_number, to_number,
                    message_body, direction, message_type, status, sent_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """

            await db.execute(
                query,
                case_uuid,
                message_id,
                from_number,
                to_number,
                message_body,
                direction,
                message_type,
                status
            )

            logger.info(f"WhatsApp message saved for case {case_id_str}")
            return True

    except Exception as e:
        logger.error(f"Error saving WhatsApp message: {e}")
        return False


async def get_case_chat_history(
    case_id: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get WhatsApp chat history for a case.

    Args:
        case_id: Case ID
        limit: Maximum number of messages to retrieve

    Returns:
        List of message dictionaries
    """
    try:
        async with get_db_session() as db:
            query = """
                SELECT
                    wm.id,
                    wm.message_id,
                    wm.from_number,
                    wm.to_number,
                    wm.message_body,
                    wm.message_type,
                    wm.direction,
                    wm.status,
                    wm.sent_at,
                    wm.delivered_at,
                    wm.read_at
                FROM whatsapp_messages wm
                INNER JOIN cases c ON wm.case_id = c.id
                WHERE c.case_id = $1
                ORDER BY wm.sent_at DESC
                LIMIT $2
            """

            rows = await db.fetch(query, case_id, limit)

            messages = []
            for row in rows:
                messages.append({
                    'id': str(row['id']),
                    'message_id': row['message_id'],
                    'from': row['from_number'],
                    'to': row['to_number'],
                    'body': row['message_body'],
                    'type': row['message_type'],
                    'direction': row['direction'],
                    'status': row['status'],
                    'sent_at': row['sent_at'].isoformat() if row['sent_at'] else None,
                    'delivered_at': row['delivered_at'].isoformat() if row['delivered_at'] else None,
                    'read_at': row['read_at'].isoformat() if row['read_at'] else None
                })

            # Reverse to get chronological order
            messages.reverse()

            return messages

    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return []


# Singleton instance
whatsapp_client = WhatsAppServiceClient()
