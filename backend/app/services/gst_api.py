"""GST API Service - Fetch company details from GST API.
Integrates with taxpayer.irisgst.com to retrieve verified GST registration data.
"""
import logging
import httpx
import re
from typing import Optional, Dict, Any
from datetime import date, datetime
from app.core.enums import EntityType

logger = logging.getLogger(__name__)


class GSTAPIService:
    """Service for fetching company details from GST API."""

    API_URL = "https://taxpayer.irisgst.com/api/search"
    API_KEY = "1719e93b-14c9-48a0-8349-cd89dc3b5311"
    TIMEOUT = 30.0

    # GSTIN pattern: 2 digits + 5 letters + 4 digits + 1 letter + 1 alphanumeric + Z + 1 alphanumeric
    GSTIN_PATTERN = r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b'

    # GST constitution to EntityType mapping
    CONSTITUTION_MAPPING = {
        "sole proprietorship": EntityType.PROPRIETORSHIP,
        "proprietorship": EntityType.PROPRIETORSHIP,
        "partnership": EntityType.PARTNERSHIP,
        "limited liability partnership": EntityType.LLP,
        "llp": EntityType.LLP,
        "private limited": EntityType.PVT_LTD,
        "private limited company": EntityType.PVT_LTD,
        "public limited": EntityType.PUBLIC_LTD,
        "public limited company": EntityType.PUBLIC_LTD,
        "one person company": EntityType.PVT_LTD,  # Map OPC to PVT_LTD
        "opc": EntityType.PVT_LTD,
        "trust": EntityType.TRUST,
        "society": EntityType.SOCIETY,
        "ngo": EntityType.SOCIETY,  # Map NGO to SOCIETY (closest match)
        "huf": EntityType.HUF,
    }

    async def fetch_company_details(self, gstin: str) -> Optional[Dict[str, Any]]:
        """
        Fetch company details from GST API.

        Args:
            gstin: 15-character GSTIN number

        Returns:
            Dict with GST data if successful, None if failed

        Response structure:
        {
            "status_code": 1,
            "gstin": "22BTTPR3963C1ZF",
            "name": "CHOKKAPU MAHESWARA RAO",
            "tradename": "LAKSHMI TRADERS",
            "registrationDate": "2024-04-04",
            "constitution": "Sole Proprietorship",
            "pradr": {
                "pncd": "494001",
                "stcd": "Chhattisgarh"
            }
        }
        """
        if not gstin or not self._validate_gstin_format(gstin):
            logger.warning(f"Invalid GSTIN format: {gstin}")
            return None

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                headers = {"apikey": self.API_KEY}
                params = {"gstin": gstin}

                logger.info(f"Calling GST API for GSTIN: {gstin}")
                response = await client.get(
                    self.API_URL,
                    headers=headers,
                    params=params
                )

                response.raise_for_status()
                data = response.json()

                # Check if API returned success
                if data.get("status_code") != 1:
                    logger.warning(f"GST API returned non-success status: {data}")
                    return None

                # Parse and enrich the response
                enriched_data = self._parse_gst_response(data)
                logger.info(f"Successfully fetched GST data for {gstin}")

                return enriched_data

        except httpx.HTTPStatusError as e:
            logger.error(f"GST API HTTP error for {gstin}: {e.response.status_code}")
            return None
        except httpx.TimeoutException:
            logger.error(f"GST API timeout for {gstin}")
            return None
        except Exception as e:
            logger.error(f"GST API error for {gstin}: {e}", exc_info=True)
            return None

    def _parse_gst_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and enrich GST API response with calculated fields.

        Args:
            data: Raw API response

        Returns:
            Enriched data with calculated fields
        """
        enriched = {
            "raw_response": data,  # Keep original for reference
            "gstin": data.get("gstin"),
            "name": data.get("name"),
            "tradename": data.get("tradename"),
            "registration_date": data.get("registrationDate"),
            "constitution": data.get("constitution"),
            "status": data.get("status", "Active"),  # Default to Active if not provided
        }

        # Extract address details
        pradr = data.get("pradr", {})
        enriched["pincode"] = pradr.get("pncd")
        enriched["state"] = pradr.get("stcd")

        # Map constitution to EntityType
        constitution = data.get("constitution", "").lower()
        entity_type = None
        for key, value in self.CONSTITUTION_MAPPING.items():
            if key in constitution:
                entity_type = value.value
                break
        enriched["entity_type"] = entity_type

        # Calculate business vintage from registration date
        if data.get("registrationDate"):
            try:
                reg_date = datetime.strptime(data["registrationDate"], "%Y-%m-%d").date()
                today = date.today()
                days_diff = (today - reg_date).days
                vintage_years = round(days_diff / 365.25, 2)
                enriched["business_vintage_years"] = max(0, vintage_years)  # Ensure non-negative
            except Exception as e:
                logger.warning(f"Failed to parse registration date: {e}")
                enriched["business_vintage_years"] = None
        else:
            enriched["business_vintage_years"] = None

        # Determine borrower name (tradename preferred, fallback to name)
        enriched["borrower_name"] = data.get("tradename") or data.get("name")

        return enriched

    def _validate_gstin_format(self, gstin: str) -> bool:
        """
        Validate GSTIN format.

        Args:
            gstin: GSTIN string

        Returns:
            True if valid format, False otherwise
        """
        if not gstin or len(gstin) != 15:
            return False

        # Check pattern
        pattern = r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$'
        return bool(re.match(pattern, gstin.upper()))

    @staticmethod
    def extract_gstin_from_text(text: str) -> Optional[str]:
        """
        Extract GSTIN from OCR text.

        Args:
            text: OCR text to search

        Returns:
            First valid GSTIN found, or None
        """
        if not text:
            return None

        # Search for GSTIN pattern
        pattern = r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b'
        matches = re.findall(pattern, text.upper())

        if matches:
            # Return first match
            return matches[0]

        return None


# Singleton instance
_gst_api_instance = None


def get_gst_api_service() -> GSTAPIService:
    """Get or create singleton GST API service instance."""
    global _gst_api_instance
    if _gst_api_instance is None:
        _gst_api_instance = GSTAPIService()
    return _gst_api_instance
