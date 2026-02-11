"""Case ID generation utility - format: CASE-YYYYMMDD-XXXX."""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.case import Case
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def generate_case_id(db: AsyncSession) -> str:
    """
    Generate a new case ID with format: CASE-YYYYMMDD-XXXX.

    The counter (XXXX) is a 4-digit sequential number that resets daily.

    Examples:
        - CASE-20240210-0001 (first case of the day)
        - CASE-20240210-0042 (42nd case of the day)
        - CASE-20240211-0001 (first case of next day)

    Args:
        db: Database session

    Returns:
        New case ID string

    Raises:
        Exception: If case ID generation fails
    """
    try:
        # Get today's date
        today = datetime.now()
        date_str = today.strftime("%Y%m%d")

        # Build the prefix for today
        prefix = f"{settings.CASE_ID_PREFIX}-{date_str}-"

        # Find the highest counter for today
        # Query for case_ids starting with today's prefix
        query = (
            select(Case.case_id)
            .where(Case.case_id.like(f"{prefix}%"))
            .order_by(Case.case_id.desc())
            .limit(1)
        )

        result = await db.execute(query)
        last_case_id = result.scalar_one_or_none()

        # Determine next counter
        if last_case_id:
            # Extract the counter from the last case ID
            # Format: CASE-YYYYMMDD-XXXX
            last_counter = int(last_case_id.split("-")[-1])
            next_counter = last_counter + 1
        else:
            # First case of the day
            next_counter = 1

        # Format counter with leading zeros (4 digits)
        counter_str = str(next_counter).zfill(4)

        # Build final case ID
        case_id = f"{prefix}{counter_str}"

        logger.info(f"Generated case ID: {case_id}")
        return case_id

    except Exception as e:
        logger.error(f"Failed to generate case ID: {e}")
        raise


async def validate_case_id_format(case_id: str) -> bool:
    """
    Validate that a case ID matches the expected format.

    Args:
        case_id: Case ID to validate

    Returns:
        True if valid, False otherwise
    """
    # Expected format: CASE-YYYYMMDD-XXXX
    parts = case_id.split("-")

    if len(parts) != 3:
        return False

    prefix, date_str, counter = parts

    # Check prefix
    if prefix != settings.CASE_ID_PREFIX:
        return False

    # Check date format (YYYYMMDD)
    if len(date_str) != 8 or not date_str.isdigit():
        return False

    try:
        datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return False

    # Check counter format (4 digits)
    if len(counter) != 4 or not counter.isdigit():
        return False

    return True
