#!/usr/bin/env python3
"""Management script for ingesting lender data from CSV files.

Usage:
    python scripts/ingest_lender_data.py --policy-csv path/to/policy.csv --pincode-csv path/to/pincodes.csv
    python scripts/ingest_lender_data.py --policy-csv-only path/to/policy.csv
    python scripts/ingest_lender_data.py --pincode-csv-only path/to/pincodes.csv
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.stage3_ingestion import (
    ingest_lender_policy_csv,
    ingest_pincode_csv,
    ingest_all_lender_data
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest lender data from CSV files into the knowledge base"
    )

    parser.add_argument(
        "--policy-csv",
        type=str,
        help="Path to the lender policy CSV file (BL Lender Policy.csv)"
    )

    parser.add_argument(
        "--pincode-csv",
        type=str,
        help="Path to the pincode serviceability CSV file"
    )

    parser.add_argument(
        "--policy-csv-only",
        type=str,
        help="Ingest only the policy CSV (don't ingest pincodes)"
    )

    parser.add_argument(
        "--pincode-csv-only",
        type=str,
        help="Ingest only the pincode CSV (requires lenders to exist in DB)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV files without inserting into database"
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    # Validate arguments
    if args.policy_csv and args.policy_csv_only:
        logger.error("Cannot specify both --policy-csv and --policy-csv-only")
        sys.exit(1)

    if args.pincode_csv and args.pincode_csv_only:
        logger.error("Cannot specify both --pincode-csv and --pincode-csv-only")
        sys.exit(1)

    # Determine mode
    policy_only = args.policy_csv_only is not None
    pincode_only = args.pincode_csv_only is not None
    both = args.policy_csv and args.pincode_csv

    if not (policy_only or pincode_only or both):
        logger.error("Must specify either:")
        logger.error("  --policy-csv AND --pincode-csv (ingest both)")
        logger.error("  --policy-csv-only (ingest policy only)")
        logger.error("  --pincode-csv-only (ingest pincodes only)")
        sys.exit(1)

    try:
        if both:
            # Ingest both files
            policy_path = args.policy_csv
            pincode_path = args.pincode_csv

            # Validate files exist
            if not Path(policy_path).exists():
                logger.error(f"Policy CSV not found: {policy_path}")
                sys.exit(1)

            if not Path(pincode_path).exists():
                logger.error(f"Pincode CSV not found: {pincode_path}")
                sys.exit(1)

            logger.info("=" * 70)
            logger.info("LENDER DATA INGESTION - FULL")
            logger.info("=" * 70)
            logger.info(f"Policy CSV:  {policy_path}")
            logger.info(f"Pincode CSV: {pincode_path}")
            logger.info("")

            if args.dry_run:
                logger.warning("DRY RUN MODE - No data will be inserted")
                logger.info("CSV validation not yet implemented")
                sys.exit(0)

            # Run ingestion
            stats = await ingest_all_lender_data(policy_path, pincode_path)

            # Print summary
            logger.info("")
            logger.info("=" * 70)
            logger.info("INGESTION COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Lenders created:  {stats['policy']['lenders_created']}")
            logger.info(f"Products created: {stats['policy']['products_created']}")
            logger.info(f"Products updated: {stats['policy']['products_updated']}")
            logger.info(f"Policy errors:    {stats['policy']['errors']}")
            logger.info("")
            logger.info(f"Lenders mapped:   {stats['pincodes']['lenders_mapped']}")
            logger.info(f"Pincodes created: {stats['pincodes']['pincodes_created']}")
            logger.info(f"Pincode errors:   {stats['pincodes']['errors']}")
            logger.info(f"Skipped non-numeric: {stats['pincodes']['skipped_non_numeric']}")

        elif policy_only:
            # Ingest policy CSV only
            policy_path = args.policy_csv_only

            if not Path(policy_path).exists():
                logger.error(f"Policy CSV not found: {policy_path}")
                sys.exit(1)

            logger.info("=" * 70)
            logger.info("LENDER POLICY INGESTION")
            logger.info("=" * 70)
            logger.info(f"Policy CSV: {policy_path}")
            logger.info("")

            if args.dry_run:
                logger.warning("DRY RUN MODE - No data will be inserted")
                logger.info("CSV validation not yet implemented")
                sys.exit(0)

            stats = await ingest_lender_policy_csv(policy_path)

            logger.info("")
            logger.info("=" * 70)
            logger.info("INGESTION COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Rows processed:   {stats['rows_processed']}")
            logger.info(f"Lenders created:  {stats['lenders_created']}")
            logger.info(f"Products created: {stats['products_created']}")
            logger.info(f"Products updated: {stats['products_updated']}")
            logger.info(f"Errors:           {stats['errors']}")

        elif pincode_only:
            # Ingest pincode CSV only
            pincode_path = args.pincode_csv_only

            if not Path(pincode_path).exists():
                logger.error(f"Pincode CSV not found: {pincode_path}")
                sys.exit(1)

            logger.info("=" * 70)
            logger.info("PINCODE SERVICEABILITY INGESTION")
            logger.info("=" * 70)
            logger.info(f"Pincode CSV: {pincode_path}")
            logger.info("")
            logger.warning("Note: This requires lenders to already exist in the database!")
            logger.warning("Run policy ingestion first if you haven't already.")
            logger.info("")

            if args.dry_run:
                logger.warning("DRY RUN MODE - No data will be inserted")
                logger.info("CSV validation not yet implemented")
                sys.exit(0)

            stats = await ingest_pincode_csv(pincode_path)

            logger.info("")
            logger.info("=" * 70)
            logger.info("INGESTION COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Lenders mapped:      {stats['lenders_mapped']}")
            logger.info(f"Pincodes created:    {stats['pincodes_created']}")
            logger.info(f"Skipped non-numeric: {stats['skipped_non_numeric']}")
            logger.info(f"Errors:              {stats['errors']}")

        logger.info("")
        logger.info("✓ Ingestion completed successfully")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
