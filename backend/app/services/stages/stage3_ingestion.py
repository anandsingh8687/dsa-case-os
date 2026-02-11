"""Stage 3: Lender Knowledge Base Ingestion Service

This module handles ingestion of lender data from CSV files:
1. Lender Policy CSV → lender_products table
2. Pincode Serviceability CSV → lender_pincodes table

The parsers handle complex field formats and normalize data for database storage.
"""

import csv
import json
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from uuid import UUID

from app.db.database import get_db_session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# LENDER NAME MAPPING
# ═══════════════════════════════════════════════════════════════

LENDER_NAME_MAP = {
    "GODREJ": "Godrej",
    "LENDINGKART": "Lendingkart",
    "FLEXILOANS": "Flexiloans",
    "INDIFI": "Indifi",
    "PROTIUM": "Protium",
    "BAJAJ": "Bajaj",
    "BAJAJ RURAL": "Bajaj",
    "ARTHMATE": "Arthmate",
    "POONAWALA": "Poonawalla",
    "POONAWALLA": "Poonawalla",
    "KREDIT BEE": "KreditBee",
    "KREDITBEE": "KreditBee",
    "AMBIT": "Ambit",
    "TATA PL": "Tata Capital",
    "TATA BL": "Tata Capital",
    "TATA CAPITAL": "Tata Capital",
    "INCRED": "InCred",
    "FIBE": "Fibe",
    "IIFL": "IIFL",
    "CLIX CAPITAL": "Clix Capital",
    "PAYSENSE": "PaySense",
    "CREDIT SAISON": "Credit Saison",
    "LOAN TAP": "LoanTap",
    "LOANTAP": "LoanTap",
    "ABFL": "ABFL",
    "L&T FINANCE": "L&T Finance",
    "OLYV": "Olyv",
    "USFB PL": "Unity Small Finance Bank",
    "USFB BL": "Unity Small Finance Bank",
    "MAS": "MAS Financial",
    "TRUCAP": "TruCap",
    "TECHFINO": "Techfino",
    "NEOGROWTH": "NeoGrowth",
    "UGRO": "UGro",
    "FT CASH": "FT Cash",
    "ICICI": "ICICI",
    "CHOLAMANDALAM": "Cholamandalam",
}


# ═══════════════════════════════════════════════════════════════
# FIELD PARSING UTILITIES
# ═══════════════════════════════════════════════════════════════

def parse_float_value(value: str) -> Optional[float]:
    """Parse a float value, handling various formats.

    Examples:
        "30L" → 30.0
        "3.5L" → 3.5
        ">=25k" → 25000.0
        "15K" → 15000.0
        "2.5" → 2.5
    """
    if not value or value.strip() in ["", "NA", "N/A", "-", "nil"]:
        return None

    value = value.strip().upper()

    # Remove >= <= > < symbols
    value = re.sub(r'^[><=]+', '', value)

    # Handle "L" suffix (Lakhs)
    if 'L' in value and 'K' not in value:
        value = value.replace('L', '').strip()
        try:
            return float(value)
        except ValueError:
            return None

    # Handle "K" suffix (thousands)
    if 'K' in value:
        value = value.replace('K', '').strip()
        try:
            return float(value) / 100  # Convert to Lakhs
        except ValueError:
            return None

    # Try direct float parsing
    try:
        return float(value)
    except ValueError:
        # Extract first number found
        match = re.search(r'[\d.]+', value)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None


def parse_integer_value(value: str) -> Optional[int]:
    """Parse an integer value, handling various formats."""
    if not value or value.strip() in ["", "NA", "N/A", "-"]:
        return None

    value = value.strip()

    # Remove >= <= > < symbols
    value = re.sub(r'^[><=]+', '', value)

    # Extract first integer found
    match = re.search(r'\d+', value)
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None

    return None


def parse_months(value: str) -> Optional[int]:
    """Parse a months value from text like '6 months', '12 month', etc."""
    if not value or value.strip() in ["", "NA", "N/A", "-"]:
        return None

    value = value.strip().lower()

    # Extract number
    match = re.search(r'(\d+)\s*(month|mon|m|yr|year)', value)
    if match:
        num = int(match.group(1))
        unit = match.group(2)

        # Convert years to months if needed
        if unit in ['yr', 'year']:
            return num * 12
        return num

    # Try direct integer
    return parse_integer_value(value)


def parse_age_range(value: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse age range like '22-65' → (22, 65)"""
    if not value or value.strip() in ["", "NA", "N/A", "-"]:
        return None, None

    value = value.strip()

    # Look for range pattern: 22-65
    match = re.search(r'(\d+)\s*[-to]+\s*(\d+)', value)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Single number
    num = parse_integer_value(value)
    if num:
        return num, num

    return None, None


def parse_entity_types(value: str) -> List[str]:
    """Parse entity types from comma-separated list.

    Examples:
        "Pvt Ltd, LLP" → ["pvt_ltd", "llp"]
        "Proprietorship, Partnership" → ["proprietorship", "partnership"]
    """
    if not value or value.strip() in ["", "NA", "N/A", "-"]:
        return []

    entities = []
    parts = value.split(',')

    for part in parts:
        part = part.strip().lower()

        # Normalize common variations
        if 'pvt' in part or 'private' in part:
            entities.append('pvt_ltd')
        elif 'llp' in part:
            entities.append('llp')
        elif 'proprietor' in part or 'proprietorship' in part:
            entities.append('proprietorship')
        elif 'partner' in part:
            entities.append('partnership')
        elif 'opc' in part:
            entities.append('opc')
        elif 'trust' in part:
            entities.append('trust')
        elif 'society' in part:
            entities.append('society')
        else:
            # Keep as-is but normalize
            entities.append(part.replace(' ', '_'))

    return entities


def parse_boolean(value: str) -> bool:
    """Parse boolean from Yes/No/Mandatory/NA."""
    if not value:
        return False

    value = value.strip().lower()
    return value in ['yes', 'mandatory', 'required', 'true', '1', 'y']


def normalize_lender_name(name: str) -> str:
    """Normalize lender name using the mapping table."""
    if not name:
        return ""

    name = name.strip().upper()
    return LENDER_NAME_MAP.get(name, name.title())


def check_policy_available(row: Dict[str, str]) -> bool:
    """Check if 'Policy not available' appears in any column."""
    for value in row.values():
        if value and 'policy not available' in str(value).lower():
            return False
    return True


# ═══════════════════════════════════════════════════════════════
# LENDER POLICY CSV INGESTION
# ═══════════════════════════════════════════════════════════════

async def ingest_lender_policy_csv(csv_path: str) -> Dict[str, int]:
    """Parse the BL Lender Policy CSV and insert into DB.

    Args:
        csv_path: Path to the lender policy CSV file

    Returns:
        Dict with stats: {"lenders_created": N, "products_created": M, "errors": K}
    """
    stats = {
        "lenders_created": 0,
        "products_created": 0,
        "products_updated": 0,
        "errors": 0,
        "rows_processed": 0
    }

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    async with get_db_session() as db:
        # Cache for lender lookups
        lender_cache: Dict[str, UUID] = {}

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (after header)
                try:
                    stats["rows_processed"] += 1

                    # Extract lender name
                    lender_name = row.get('Lender', '').strip()
                    if not lender_name:
                        logger.warning(f"Row {row_num}: Missing lender name, skipping")
                        stats["errors"] += 1
                        continue

                    lender_name = normalize_lender_name(lender_name)

                    # Get or create lender
                    lender_id = await _get_or_create_lender(db, lender_name, lender_cache)
                    if lender_id:
                        stats["lenders_created"] += 1

                    # Parse product data
                    product_data = _parse_lender_policy_row(row, lender_name)

                    # Insert or update product
                    created = await _upsert_lender_product(
                        db,
                        lender_cache[lender_name],
                        product_data
                    )

                    if created:
                        stats["products_created"] += 1
                    else:
                        stats["products_updated"] += 1

                    logger.info(
                        f"Row {row_num}: Processed {lender_name} - "
                        f"{product_data.get('product_name', 'Unknown')}"
                    )

                except Exception as e:
                    logger.error(f"Row {row_num}: Error processing - {e}", exc_info=True)
                    stats["errors"] += 1

        # Note: asyncpg auto-commits each statement, no explicit commit needed

    return stats


def _parse_lender_policy_row(row: Dict[str, str], lender_name: str) -> Dict[str, Any]:
    """Parse a single row from the lender policy CSV."""

    product_name = row.get('Product Program', '').strip() or 'BL'

    # Parse all fields
    data = {
        'product_name': product_name,
        'policy_available': check_policy_available(row),
    }

    # Numeric fields
    data['min_vintage_years'] = parse_float_value(row.get('Min. Vintage', ''))
    data['min_cibil_score'] = parse_integer_value(row.get('Min. Score', ''))
    data['min_turnover_annual'] = parse_float_value(row.get('Min. Turnover', ''))
    data['max_ticket_size'] = parse_float_value(row.get('Max Ticket size', ''))
    data['disb_till_date'] = parse_float_value(row.get('Disb Till date', ''))
    data['minimum_turnover_alt'] = parse_float_value(row.get('Minimum Turnover', ''))

    # ABB (Average Bank Balance)
    abb_value = row.get('ABB', '').strip()
    if abb_value and abb_value not in ['', 'NA', '-']:
        # If it contains ratio info, split it
        if 'or' in abb_value.lower() or 'ratio' in abb_value.lower():
            parts = abb_value.split('or')
            if len(parts) >= 1:
                data['min_abb'] = parse_float_value(parts[0])
            if len(parts) >= 2:
                data['abb_to_emi_ratio'] = parts[1].strip()
        else:
            data['min_abb'] = parse_float_value(abb_value)

    # Entity types
    entity_str = row.get('Entity', '')
    data['eligible_entity_types'] = parse_entity_types(entity_str)

    # Age range
    age_min, age_max = parse_age_range(row.get('Age', ''))
    data['age_min'] = age_min
    data['age_max'] = age_max

    # DPD fields
    data['no_30plus_dpd_months'] = parse_months(row.get('No 30+', ''))
    data['no_60plus_dpd_months'] = parse_months(row.get('60+', ''))
    data['no_90plus_dpd_months'] = parse_months(row.get('90+', ''))

    # Bureau and enquiry rules (keep as text)
    data['max_enquiries_rule'] = row.get('Enquiries', '').strip() or None
    data['emi_bounce_rule'] = row.get('EMI bounce', '').strip() or None
    data['bureau_check_detail'] = row.get('Bureau Check', '').strip() or None
    data['max_overdue_amount'] = parse_float_value(row.get('No Overdues', ''))

    # Banking requirements
    data['banking_months_required'] = parse_months(row.get('Banking Statement', ''))
    data['bank_source_type'] = row.get('Bank Source', '').strip() or None

    # Document requirements (boolean)
    data['ownership_proof_required'] = parse_boolean(row.get('Ownership Proof', ''))
    data['ownership_proof_detail'] = row.get('Ownership Proof', '').strip() or None
    data['gst_required'] = parse_boolean(row.get('GST', ''))
    data['gst_detail'] = row.get('GST', '').strip() or None

    # Verification requirements
    data['tele_pd_required'] = parse_boolean(row.get('Tele PD', ''))
    data['video_kyc_required'] = parse_boolean(row.get('Video KYC', ''))
    data['fi_required'] = parse_boolean(row.get('FI', ''))
    data['fi_detail'] = row.get('FI', '').strip() or None

    # KYC documents
    data['kyc_documents'] = row.get('KYC Doc', '').strip() or None

    # Tenor (tenure)
    data['tenor_min_months'] = parse_integer_value(row.get('Tenor Min', ''))
    data['tenor_max_months'] = parse_integer_value(row.get('Tenor Max', ''))

    # Infer program type from product name
    product_lower = product_name.lower()
    if 'digital' in product_lower or 'banking' in product_lower:
        data['program_type'] = 'banking'
    elif 'income' in product_lower or 'itr' in product_lower:
        data['program_type'] = 'income'
    else:
        data['program_type'] = 'hybrid'

    return data


async def _get_or_create_lender(
    db,
    lender_name: str,
    cache: Dict[str, UUID]
) -> Optional[UUID]:
    """Get or create a lender, using cache for performance.

    Returns:
        UUID if newly created, None if already existed
    """
    if lender_name in cache:
        return None  # Already exists

    # Check if exists in DB
    row = await db.fetchrow(
        "SELECT id FROM lenders WHERE lender_name = $1",
        lender_name
    )

    if row:
        cache[lender_name] = row['id']
        return None

    # Create new lender
    lender_code = lender_name.upper().replace(' ', '_')[:20]

    row = await db.fetchrow(
        """
        INSERT INTO lenders (lender_name, lender_code, is_active)
        VALUES ($1, $2, TRUE)
        RETURNING id
        """,
        lender_name,
        lender_code
    )
    lender_id = row['id']
    cache[lender_name] = lender_id

    logger.info(f"Created new lender: {lender_name} (ID: {lender_id})")
    return lender_id


async def _upsert_lender_product(
    db,
    lender_id: UUID,
    product_data: Dict[str, Any]
) -> bool:
    """Insert or update a lender product.

    Returns:
        True if created, False if updated
    """
    product_name = product_data['product_name']

    # Check if exists
    row = await db.fetchrow(
        """
        SELECT id FROM lender_products
        WHERE lender_id = $1 AND product_name = $2
        """,
        lender_id,
        product_name
    )

    # Build field lists for SQL — convert lists to JSON strings for JSONB columns
    JSONB_FIELDS = {'eligible_entity_types', 'eligible_industries', 'excluded_industries', 'required_documents', 'missing_for_improvement'}
    fields = list(product_data.keys())
    processed_data = {}
    for f in fields:
        v = product_data[f]
        if f in JSONB_FIELDS and isinstance(v, (list, dict)):
            processed_data[f] = json.dumps(v)
        else:
            processed_data[f] = v

    if row:
        # Update existing
        set_clause = ', '.join(f"{field} = ${i+3}" for i, field in enumerate(fields))
        values = [lender_id, product_name] + [processed_data[f] for f in fields]

        await db.execute(
            f"""
            UPDATE lender_products
            SET {set_clause}, updated_at = NOW()
            WHERE lender_id = $1 AND product_name = $2
            """,
            *values
        )
        return False
    else:
        # Insert new
        fields_with_lender = ['lender_id'] + fields
        placeholders = ', '.join(f'${i+1}' for i in range(len(fields_with_lender)))
        field_names = ', '.join(fields_with_lender)
        values = [lender_id] + [processed_data[f] for f in fields]

        await db.execute(
            f"""
            INSERT INTO lender_products ({field_names})
            VALUES ({placeholders})
            """,
            *values
        )
        return True


# ═══════════════════════════════════════════════════════════════
# PINCODE SERVICEABILITY CSV INGESTION
# ═══════════════════════════════════════════════════════════════

async def ingest_pincode_csv(csv_path: str) -> Dict[str, int]:
    """Parse the pincode CSV and insert into lender_pincodes table.

    The CSV structure is unusual - each column is a lender, and cells contain pincodes.

    Args:
        csv_path: Path to the pincode CSV file

    Returns:
        Dict with stats: {"lenders_mapped": N, "pincodes_created": M, "errors": K}
    """
    stats = {
        "lenders_mapped": 0,
        "pincodes_created": 0,
        "skipped_non_numeric": 0,
        "errors": 0
    }

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    async with get_db_session() as db:
        # Get all lenders from DB
        rows = await db.fetch("SELECT id, lender_name FROM lenders")
        lenders_by_name = {row['lender_name'].upper(): row['id'] for row in rows}

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

            if not headers:
                raise ValueError("CSV file has no headers")

            # Process each column (each column = a lender)
            for column_header in headers:
                column_header_clean = column_header.strip()
                if not column_header_clean:
                    continue

                # Normalize lender name
                normalized_name = normalize_lender_name(column_header_clean)

                # Find lender ID
                lender_id = None
                for db_name, db_id in lenders_by_name.items():
                    if normalized_name.upper() in db_name or db_name in normalized_name.upper():
                        lender_id = db_id
                        break

                if not lender_id:
                    logger.warning(
                        f"Column '{column_header_clean}' - No matching lender found in DB"
                    )
                    stats["errors"] += 1
                    continue

                stats["lenders_mapped"] += 1

                # Collect all pincodes from this column
                pincodes = []
                f.seek(0)  # Reset file pointer
                next(reader)  # Skip header

                for row in reader:
                    pincode_value = row.get(column_header, '').strip()

                    if not pincode_value:
                        continue

                    # Check if it's numeric (valid pincode)
                    if not re.match(r'^\d{6}$', pincode_value):
                        # Might be a city name or invalid data
                        stats["skipped_non_numeric"] += 1
                        continue

                    pincodes.append(pincode_value)

                # Bulk insert pincodes for this lender
                if pincodes:
                    inserted = await _bulk_insert_pincodes(
                        db,
                        lender_id,
                        column_header_clean,
                        pincodes
                    )
                    stats["pincodes_created"] += inserted

                    logger.info(
                        f"Lender '{normalized_name}': Inserted {inserted} pincodes"
                    )

        # Note: asyncpg auto-commits each statement, no explicit commit needed

    return stats


async def _bulk_insert_pincodes(
    db,
    lender_id: UUID,
    column_name: str,
    pincodes: List[str]
) -> int:
    """Bulk insert pincodes for a lender, handling duplicates."""
    inserted = 0

    for pincode in pincodes:
        try:
            await db.execute(
                """
                INSERT INTO lender_pincodes (lender_id, lender_column_name, pincode)
                VALUES ($1, $2, $3)
                ON CONFLICT (lender_id, pincode) DO NOTHING
                """,
                lender_id,
                column_name,
                pincode
            )
            inserted += 1
        except Exception as e:
            logger.error(f"Error inserting pincode {pincode}: {e}")

    return inserted


# ═══════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════════════

async def ingest_all_lender_data(
    policy_csv_path: str,
    pincode_csv_path: str
) -> Dict[str, Any]:
    """Convenience function to ingest both CSV files.

    Args:
        policy_csv_path: Path to lender policy CSV
        pincode_csv_path: Path to pincode serviceability CSV

    Returns:
        Combined stats from both ingestions
    """
    logger.info("Starting lender data ingestion...")

    # Ingest lender policy first
    logger.info("Step 1: Ingesting lender policy CSV...")
    policy_stats = await ingest_lender_policy_csv(policy_csv_path)

    # Ingest pincodes
    logger.info("Step 2: Ingesting pincode serviceability CSV...")
    pincode_stats = await ingest_pincode_csv(pincode_csv_path)

    combined_stats = {
        "policy": policy_stats,
        "pincodes": pincode_stats,
        "success": True
    }

    logger.info("Lender data ingestion complete!")
    logger.info(f"  Lenders created: {policy_stats['lenders_created']}")
    logger.info(f"  Products created: {policy_stats['products_created']}")
    logger.info(f"  Products updated: {policy_stats['products_updated']}")
    logger.info(f"  Pincodes created: {pincode_stats['pincodes_created']}")
    logger.info(f"  Total errors: {policy_stats['errors'] + pincode_stats['errors']}")

    return combined_stats
