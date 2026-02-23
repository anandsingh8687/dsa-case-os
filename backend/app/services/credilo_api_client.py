"""Client for Credilo parser API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from app.core.config import settings


class CrediloApiError(RuntimeError):
    """Raised when Credilo API calls fail."""


class CrediloApiClient:
    """Thin HTTP client for Credilo parser endpoints."""

    def __init__(self) -> None:
        self.base_url = (settings.CREDILO_API_BASE_URL or "").strip().rstrip("/") + "/"
        self.process_url = self._build_url(settings.CREDILO_PROCESS_PATH)
        self.preview_url = self._build_url(settings.CREDILO_PREVIEW_PATH)
        self.timeout_seconds = float(settings.CREDILO_TIMEOUT_SECONDS)

    def _build_url(self, path_or_url: str) -> str:
        raw = (path_or_url or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        if not self.base_url:
            return raw
        return urljoin(self.base_url, raw.lstrip("/"))

    def is_configured(self) -> bool:
        return bool(self.preview_url)

    async def process_preview(self, pdf_paths: List[str]) -> Dict[str, Any]:
        """Send PDFs to Credilo preview endpoint and return JSON payload."""
        files = []
        file_handles = []
        for path in pdf_paths:
            p = Path(path)
            if not p.exists() or not p.is_file():
                continue
            handle = p.open("rb")
            file_handles.append(handle)
            files.append(("files", (p.name, handle, "application/pdf")))

        if not files:
            raise CrediloApiError("No valid PDF files found for Credilo preview upload")

        if not self.preview_url:
            raise CrediloApiError("Credilo preview URL is not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.preview_url, files=files)
        finally:
            for handle in file_handles:
                handle.close()

        if response.status_code != 200:
            detail = response.text.strip()[:1200]
            raise CrediloApiError(
                f"Credilo preview failed ({response.status_code}): {detail}"
            )

        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            raise CrediloApiError(
                f"Unexpected Credilo preview content-type: {content_type or 'unknown'}"
            )

        try:
            payload = response.json()
        except Exception as exc:  # pragma: no cover - defensive path
            raise CrediloApiError(f"Invalid JSON from Credilo preview: {exc}") from exc

        if not isinstance(payload, dict):
            raise CrediloApiError("Credilo preview payload is not a JSON object")
        return payload

    async def process_excel(self, pdf_paths: List[str]) -> bytes:
        """Send PDFs to Credilo process endpoint and return XLSX bytes."""
        files = []
        file_handles = []
        for path in pdf_paths:
            p = Path(path)
            if not p.exists() or not p.is_file():
                continue
            handle = p.open("rb")
            file_handles.append(handle)
            files.append(("files", (p.name, handle, "application/pdf")))

        if not files:
            raise CrediloApiError("No valid PDF files found for Credilo process upload")

        if not self.process_url:
            raise CrediloApiError("Credilo process URL is not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.process_url, files=files)
        finally:
            for handle in file_handles:
                handle.close()

        if response.status_code != 200:
            detail = response.text.strip()[:1200]
            raise CrediloApiError(
                f"Credilo process failed ({response.status_code}): {detail}"
            )

        content_type = response.headers.get("content-type", "").lower()
        if "spreadsheetml" not in content_type and "excel" not in content_type:
            raise CrediloApiError(
                f"Unexpected Credilo process content-type: {content_type or 'unknown'}"
            )

        return response.content
