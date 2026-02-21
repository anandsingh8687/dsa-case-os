"""
Bank Statement Analyzer endpoints - Proxy to external processing API
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import httpx
import logging

from app.services.credilo_api_client import CrediloApiClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bank-statement", tags=["bank-statement"])

_credilo_client = CrediloApiClient()
EXTERNAL_API_URL = _credilo_client.process_url
EXTERNAL_API_TIMEOUT_SECONDS = _credilo_client.timeout_seconds


@router.post("/process")
async def process_bank_statements(
    files: List[UploadFile] = File(...)
):
    """
    Proxy endpoint to forward bank statement files to external processing API.
    This avoids CORS issues by making the request from backend.
    """
    try:
        if not EXTERNAL_API_URL:
            raise HTTPException(
                status_code=503,
                detail="Credilo process endpoint is not configured",
            )

        logger.info(f"Received {len(files)} file(s) for bank statement processing")

        # Prepare files for forwarding
        files_to_send = []
        for file in files:
            content = await file.read()
            files_to_send.append(
                ("files", (file.filename, content, file.content_type))
            )
            logger.info(f"Prepared file: {file.filename} ({len(content)} bytes)")

        # Forward request to external API
        async with httpx.AsyncClient(timeout=EXTERNAL_API_TIMEOUT_SECONDS) as client:
            logger.info(f"Forwarding request to {EXTERNAL_API_URL}")
            response = await client.post(
                EXTERNAL_API_URL,
                files=files_to_send
            )

            logger.info(f"External API response status: {response.status_code}")
            logger.info(f"External API response headers: {dict(response.headers)}")

            # Check if response is successful
            if response.status_code != 200:
                logger.error(f"External API error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"External API error: {response.text}"
                )

            # Check content type to determine response format
            content_type = response.headers.get("content-type", "")

            if "spreadsheet" in content_type or "excel" in content_type or content_type.startswith("application/vnd"):
                # Excel file response - return as streaming response
                logger.info("Returning Excel file response")
                return StreamingResponse(
                    iter([response.content]),
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="bank_statement_analysis.xlsx"'
                    }
                )
            elif "json" in content_type:
                # JSON response - return as JSON
                logger.info("Returning JSON response")
                return response.json()
            else:
                # Unknown format - return raw content
                logger.warning(f"Unknown content type: {content_type}")
                return StreamingResponse(
                    iter([response.content]),
                    media_type=content_type
                )

    except httpx.TimeoutException:
        logger.error("Request to external API timed out after %.0fs", EXTERNAL_API_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=504,
            detail=(
                "Bank statement analyzer timed out while processing this file set. "
                "Try smaller batches (1-3 statements) and re-run."
            )
        )
    except httpx.RequestError as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to external API: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
