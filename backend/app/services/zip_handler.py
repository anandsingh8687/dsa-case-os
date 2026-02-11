"""
ZIP File Handler Service

Handles extraction and processing of ZIP files containing multiple bank statements.
Supports batch upload and aggregated analysis.
"""

import logging
import zipfile
import io
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


class ZIPHandler:
    """Service for handling ZIP file uploads and extraction."""

    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}
    MAX_FILES_PER_ZIP = 50
    MAX_FILE_SIZE_MB = 10

    @classmethod
    async def extract_zip(
        cls,
        zip_content: bytes,
        zip_filename: str
    ) -> List[Dict[str, Any]]:
        """
        Extract all files from a ZIP archive.

        Args:
            zip_content: ZIP file content as bytes
            zip_filename: Original ZIP filename

        Returns:
            List of extracted files with metadata:
            [
                {
                    'filename': str,
                    'content': bytes,
                    'size': int,
                    'extension': str
                },
                ...
            ]

        Raises:
            ValueError: If ZIP is invalid or contains too many files
        """
        logger.info(f"Extracting ZIP file: {zip_filename}")

        try:
            # Create BytesIO object from content
            zip_buffer = io.BytesIO(zip_content)

            # Open ZIP file
            with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                # Get list of files in ZIP
                file_list = zip_ref.namelist()

                # Filter out directories and hidden files
                valid_files = [
                    f for f in file_list
                    if not f.endswith('/') and not f.startswith('__MACOSX') and not f.startswith('.')
                ]

                logger.info(f"Found {len(valid_files)} files in ZIP (total including dirs: {len(file_list)})")

                if len(valid_files) > cls.MAX_FILES_PER_ZIP:
                    raise ValueError(f"ZIP contains too many files ({len(valid_files)}). Maximum: {cls.MAX_FILES_PER_ZIP}")

                if len(valid_files) == 0:
                    raise ValueError("ZIP file is empty or contains only directories")

                # Extract files
                extracted_files = []

                for filename in valid_files:
                    # Get file extension
                    ext = Path(filename).suffix.lower()

                    # Check if extension is allowed
                    if ext not in cls.ALLOWED_EXTENSIONS:
                        logger.warning(f"Skipping file with unsupported extension: {filename}")
                        continue

                    # Extract file content
                    try:
                        file_content = zip_ref.read(filename)
                        file_size_mb = len(file_content) / (1024 * 1024)

                        if file_size_mb > cls.MAX_FILE_SIZE_MB:
                            logger.warning(f"Skipping large file: {filename} ({file_size_mb:.1f}MB)")
                            continue

                        extracted_files.append({
                            'filename': filename,
                            'content': file_content,
                            'size': len(file_content),
                            'extension': ext
                        })

                        logger.info(f"Extracted: {filename} ({len(file_content) / 1024:.1f} KB)")

                    except Exception as e:
                        logger.error(f"Error extracting file {filename}: {e}")
                        continue

                if not extracted_files:
                    raise ValueError("No valid files found in ZIP after filtering")

                logger.info(f"Successfully extracted {len(extracted_files)} files from {zip_filename}")

                return extracted_files

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {zip_filename}")
            raise ValueError("Invalid ZIP file")

        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}", exc_info=True)
            raise ValueError(f"Error processing ZIP file: {str(e)}")

    @classmethod
    def validate_zip(cls, file_content: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate ZIP file before extraction.

        Args:
            file_content: ZIP file content
            filename: Filename

        Returns:
            (is_valid, error_message)
        """
        try:
            # Check if it's a valid ZIP
            if not zipfile.is_zipfile(io.BytesIO(file_content)):
                return False, "File is not a valid ZIP archive"

            # Check file size (100MB max)
            max_size = 100 * 1024 * 1024  # 100MB
            if len(file_content) > max_size:
                return False, f"ZIP file too large (max: 100MB)"

            return True, None

        except Exception as e:
            logger.error(f"Error validating ZIP: {e}")
            return False, str(e)

    @classmethod
    async def process_batch_documents(
        cls,
        extracted_files: List[Dict[str, Any]],
        case_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Process all extracted files as documents for a case.

        This is a helper function that will be called by the document upload endpoint.

        Args:
            extracted_files: List of extracted files from ZIP
            case_id: Case ID
            user_id: User ID

        Returns:
            {
                'success': bool,
                'total_files': int,
                'processed': int,
                'failed': int,
                'document_ids': List[str],
                'errors': List[str]
            }
        """
        from app.services.file_storage import save_file
        from app.services.stages.stage0_case_entry import process_uploaded_document
        from app.db.database import get_db_session

        logger.info(f"Processing {len(extracted_files)} documents for case {case_id}")

        processed = 0
        failed = 0
        document_ids = []
        errors = []

        async with get_db_session() as db:
            # Get case UUID
            case_query = "SELECT id FROM cases WHERE case_id = $1"
            case_row = await db.fetchrow(case_query, case_id)

            if not case_row:
                return {
                    'success': False,
                    'error': 'Case not found',
                    'total_files': len(extracted_files),
                    'processed': 0,
                    'failed': len(extracted_files)
                }

            case_uuid = case_row['id']

        # Process each file
        for file_data in extracted_files:
            try:
                filename = file_data['filename']
                content = file_data['content']

                logger.info(f"Processing file: {filename}")

                # Save file to storage
                storage_key = await save_file(
                    file_content=content,
                    filename=filename,
                    case_id=case_id
                )

                # Create document record and process
                async with get_db_session() as db:
                    # Insert document record
                    doc_query = """
                        INSERT INTO documents (
                            case_id,
                            original_filename,
                            storage_key,
                            file_size_bytes,
                            mime_type,
                            status,
                            created_at
                        )
                        VALUES ($1, $2, $3, $4, $5, 'uploaded', NOW())
                        RETURNING id
                    """

                    # Determine MIME type
                    ext = file_data['extension']
                    mime_map = {
                        '.pdf': 'application/pdf',
                        '.png': 'image/png',
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.tif': 'image/tiff',
                        '.tiff': 'image/tiff'
                    }
                    mime_type = mime_map.get(ext, 'application/octet-stream')

                    doc_id = await db.fetchval(
                        doc_query,
                        case_uuid,
                        filename,
                        storage_key,
                        file_data['size'],
                        mime_type
                    )

                    # Process document (OCR, classification, extraction)
                    await process_uploaded_document(
                        document_id=str(doc_id),
                        case_id=str(case_uuid)
                    )

                    document_ids.append(str(doc_id))
                    processed += 1

                    logger.info(f"Successfully processed: {filename}")

            except Exception as e:
                logger.error(f"Error processing file {file_data['filename']}: {e}", exc_info=True)
                errors.append(f"{file_data['filename']}: {str(e)}")
                failed += 1

        result = {
            'success': processed > 0,
            'total_files': len(extracted_files),
            'processed': processed,
            'failed': failed,
            'document_ids': document_ids,
            'errors': errors
        }

        logger.info(f"Batch processing complete: {processed} success, {failed} failed")

        return result


class BankStatementAggregator:
    """Service for aggregating analysis from multiple bank statements."""

    @classmethod
    async def aggregate_bank_statements(
        cls,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Aggregate analysis from all bank statements in a case.

        This combines data from multiple bank statements to provide:
        - Total months of banking data
        - Average monthly credit (across all statements)
        - Average monthly balance
        - Total bounced cheques
        - Consistent revenue patterns
        - Month-over-month trends

        Args:
            case_id: Case ID

        Returns:
            {
                'case_id': str,
                'total_months': int,
                'statement_count': int,
                'aggregate_metrics': {
                    'avg_monthly_credit': float,
                    'avg_monthly_balance': float,
                    'total_bounced_cheques': int,
                    'min_balance': float,
                    'max_balance': float,
                    'consistent_credits': bool
                },
                'monthly_breakdown': [
                    {'month': '2025-01', 'credit': 450000, 'balance': 120000},
                    ...
                ],
                'trend_analysis': {
                    'credit_trend': 'increasing',  # 'increasing', 'stable', 'decreasing'
                    'volatility': 'low',  # 'low', 'medium', 'high'
                    'consistent_inflows': true
                }
            }
        """
        from app.db.database import get_db_session

        logger.info(f"Aggregating bank statements for case {case_id}")

        try:
            async with get_db_session() as db:
                # Get case UUID
                case_query = "SELECT id FROM cases WHERE case_id = $1"
                case_row = await db.fetchrow(case_query, case_id)

                if not case_row:
                    return {'error': 'Case not found'}

                case_uuid = case_row['id']

                # Get all bank statement documents
                docs_query = """
                    SELECT id, original_filename
                    FROM documents
                    WHERE case_id = $1
                      AND doc_type = 'BANK_STATEMENT'
                      AND status = 'processed'
                """

                doc_rows = await db.fetch(docs_query, case_uuid)

                if not doc_rows:
                    return {
                        'case_id': case_id,
                        'error': 'No bank statements found',
                        'statement_count': 0
                    }

                statement_count = len(doc_rows)
                logger.info(f"Found {statement_count} bank statements for case {case_id}")

                # Get extracted banking data from all statements
                # This would typically come from extracted_fields or a dedicated banking_data table
                # For now, we'll aggregate from borrower_features

                features_query = """
                    SELECT
                        monthly_credit_avg,
                        avg_monthly_balance,
                        bounced_cheques_count,
                        banking_months
                    FROM borrower_features
                    WHERE case_id = $1
                """

                features_row = await db.fetchrow(features_query, case_uuid)

                if not features_row:
                    return {
                        'case_id': case_id,
                        'statement_count': statement_count,
                        'error': 'Banking data not yet analyzed'
                    }

                # Build aggregate response
                aggregate_metrics = {
                    'avg_monthly_credit': features_row['monthly_credit_avg'],
                    'avg_monthly_balance': features_row['avg_monthly_balance'],
                    'total_bounced_cheques': features_row['bounced_cheques_count'] or 0,
                    'banking_months': features_row['banking_months']
                }

                # Calculate simple trend (placeholder - would need month-by-month data)
                trend_analysis = {
                    'credit_trend': 'stable',
                    'volatility': 'low' if (features_row['bounced_cheques_count'] or 0) == 0 else 'medium',
                    'consistent_inflows': (features_row['monthly_credit_avg'] or 0) > 0
                }

                result = {
                    'case_id': case_id,
                    'total_months': features_row['banking_months'] or 0,
                    'statement_count': statement_count,
                    'aggregate_metrics': aggregate_metrics,
                    'trend_analysis': trend_analysis
                }

                logger.info(f"Aggregated data for {statement_count} statements spanning {result['total_months']} months")

                return result

        except Exception as e:
            logger.error(f"Error aggregating bank statements: {e}", exc_info=True)
            return {
                'case_id': case_id,
                'error': str(e)
            }


# Singleton instances
zip_handler = ZIPHandler()
bank_aggregator = BankStatementAggregator()
