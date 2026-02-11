# Stage 0: Case Entry (Chaos Ingestion) Module

## Overview

Stage 0 is the file upload and case creation module for the DSA Case OS. It handles messy, real-world document uploads and creates structured Case objects with intelligent file processing.

## Features

### Case Management
- **Automatic Case ID Generation**: Format `CASE-YYYYMMDD-XXXX` (4-digit sequential daily counter)
- **User-based Case Isolation**: Each user's cases are separate
- **Manual Override Support**: Update case fields with manual corrections
- **Soft Delete**: Cases can be deactivated without losing data

### File Upload
- **Supported Formats**: PDF, JPG, JPEG, PNG, TIFF, ZIP
- **ZIP Extraction**: Automatically extracts and flattens nested folder structures
- **Duplicate Detection**: SHA-256 hash-based deduplication per case
- **File Size Validation**:
  - Max 25MB per file
  - Max 100MB per case upload
- **Smart Filtering**: Ignores `.DS_Store`, `__MACOSX`, and other junk files

### Storage
- **Local Filesystem**: Default implementation with organized directory structure
- **S3 Ready**: Abstract interface for future S3 integration
- **Storage Structure**: `{base_path}/{case_id}/{filename}`

## Project Structure

```
backend/
├── app/
│   ├── api/v1/endpoints/
│   │   └── cases.py              # FastAPI endpoints
│   ├── models/
│   │   ├── base.py               # SQLAlchemy Base
│   │   └── case.py               # Case and Document models
│   ├── services/
│   │   ├── file_storage.py       # File storage abstraction
│   │   └── stages/
│   │       └── stage0_case_entry.py  # Core business logic
│   ├── utils/
│   │   └── case_id_generator.py  # Case ID generation
│   ├── schemas/
│   │   └── shared.py             # Pydantic schemas
│   ├── core/
│   │   ├── config.py             # Configuration
│   │   └── enums.py              # Shared enums
│   └── db/
│       ├── schema.sql            # Database schema
│       └── database.py           # Database connection
└── tests/
    ├── conftest.py               # Test fixtures
    └── test_stage0.py            # Unit tests
```

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing
```

### 2. Database Setup

```bash
# Create database
createdb dsa_case_os

# Run schema (if not using Alembic migrations)
psql dsa_case_os < app/db/schema.sql
```

### 3. Configuration

Create a `.env` file:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os

# File Storage
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./uploads
MAX_FILE_SIZE_MB=25
MAX_CASE_UPLOAD_MB=100

# Application
DEBUG=True
SECRET_KEY=your-secret-key
```

### 4. Run the Application

```bash
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

### Create Case
```http
POST /api/v1/cases/
Content-Type: application/json

{
  "borrower_name": "John Doe",
  "entity_type": "proprietorship",
  "program_type": "banking",
  "loan_amount_requested": 500000
}
```

**Response:**
```json
{
  "id": "uuid",
  "case_id": "CASE-20240210-0001",
  "status": "created",
  "borrower_name": "John Doe",
  "completeness_score": 0.0,
  "created_at": "2024-02-10T10:00:00Z"
}
```

### Upload Files
```http
POST /api/v1/cases/{case_id}/upload
Content-Type: multipart/form-data

files: [file1.pdf, file2.jpg, archive.zip]
```

**Response:**
```json
[
  {
    "id": "uuid",
    "original_filename": "file1.pdf",
    "doc_type": "unknown",
    "status": "uploaded",
    "created_at": "2024-02-10T10:01:00Z"
  }
]
```

### List Cases
```http
GET /api/v1/cases/
```

### Get Case Details
```http
GET /api/v1/cases/{case_id}
```

### Update Case
```http
PATCH /api/v1/cases/{case_id}
Content-Type: application/json

{
  "borrower_name": "Updated Name",
  "cibil_score_manual": 750
}
```

### Delete Case
```http
DELETE /api/v1/cases/{case_id}
```

## Testing

### Run All Tests
```bash
cd backend
pytest
```

### Run Specific Test File
```bash
pytest tests/test_stage0.py
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html
```

### Test Categories

1. **Case ID Generation** - Sequential daily counter logic
2. **Case Creation** - Minimal and full data scenarios
3. **File Upload** - Single files, multiple files, various formats
4. **ZIP Handling** - Extraction, flattening, filtering
5. **File Validation** - Size limits, extension filtering
6. **Duplicate Detection** - Hash-based deduplication
7. **Case Retrieval** - Get, list operations
8. **Case Updates** - Manual overrides
9. **Case Deletion** - Soft delete

## Usage Examples

### Python Client Example

```python
import httpx

# Create a case
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/v1/cases/",
        json={
            "borrower_name": "Jane Doe",
            "entity_type": "proprietorship"
        }
    )
    case = response.json()
    case_id = case["case_id"]

    # Upload files
    files = [
        ("files", open("pan.pdf", "rb")),
        ("files", open("gst.pdf", "rb")),
        ("files", open("bank_statements.zip", "rb"))
    ]

    response = await client.post(
        f"http://localhost:8000/api/v1/cases/{case_id}/upload",
        files=files
    )
    documents = response.json()
    print(f"Uploaded {len(documents)} documents")
```

### cURL Examples

```bash
# Create case
curl -X POST http://localhost:8000/api/v1/cases/ \
  -H "Content-Type: application/json" \
  -d '{"borrower_name": "Test User"}'

# Upload files
curl -X POST http://localhost:8000/api/v1/cases/CASE-20240210-0001/upload \
  -F "files=@document1.pdf" \
  -F "files=@document2.jpg" \
  -F "files=@archive.zip"

# List cases
curl http://localhost:8000/api/v1/cases/

# Get case details
curl http://localhost:8000/api/v1/cases/CASE-20240210-0001

# Update case
curl -X PATCH http://localhost:8000/api/v1/cases/CASE-20240210-0001 \
  -H "Content-Type: application/json" \
  -d '{"cibil_score_manual": 750}'

# Delete case
curl -X DELETE http://localhost:8000/api/v1/cases/CASE-20240210-0001
```

## Architecture Details

### Case ID Generation
- Format: `CASE-YYYYMMDD-XXXX`
- Counter resets daily
- Thread-safe via database queries
- Validated on input

### File Storage
- **Abstract Interface**: `FileStorageBackend`
- **Local Implementation**: `LocalFileStorage`
  - Organized by case ID
  - Handles duplicates with counter suffix
  - Returns storage_key for DB reference
- **Future S3**: `S3FileStorage` (stub created)

### Duplicate Detection
- SHA-256 hash computed on upload
- Checked against existing documents in same case
- Duplicates logged but not stored
- Hash stored in DB for future reference

### ZIP Processing
1. Validate ZIP file
2. Extract all files
3. Skip ignored files/folders
4. Flatten directory structure
5. Validate each extracted file
6. Process like regular uploads
7. Detect duplicates across all files

### Error Handling
- File too large → Skip with warning
- Unsupported format → Skip with warning
- Invalid ZIP → HTTP 400
- Case not found → HTTP 404
- Database errors → HTTP 500
- All errors logged with context

## Database Schema

### Cases Table
```sql
CREATE TABLE cases (
    id              UUID PRIMARY KEY,
    case_id         VARCHAR(20) UNIQUE NOT NULL,
    user_id         UUID NOT NULL,
    status          VARCHAR(30) DEFAULT 'created',
    borrower_name   VARCHAR(255),
    -- ... (see schema.sql for full definition)
);
```

### Documents Table
```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY,
    case_id         UUID REFERENCES cases(id) ON DELETE CASCADE,
    original_filename VARCHAR(512),
    storage_key     VARCHAR(512) NOT NULL,
    file_hash       VARCHAR(64),
    doc_type        VARCHAR(30) DEFAULT 'unknown',
    status          VARCHAR(20) DEFAULT 'uploaded',
    -- ... (see schema.sql for full definition)
);
```

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `STORAGE_BACKEND` | `local` | Storage type: `local` or `s3` |
| `LOCAL_STORAGE_PATH` | `./uploads` | Local filesystem path |
| `MAX_FILE_SIZE_MB` | `25` | Max size per file |
| `MAX_CASE_UPLOAD_MB` | `100` | Max total upload size |
| `ALLOWED_EXTENSIONS` | `[pdf, jpg, jpeg, png, tiff, zip]` | Allowed file types |
| `CASE_ID_PREFIX` | `CASE` | Prefix for case IDs |

## Logging

All operations are logged with context:

```python
logger.info(f"Generated case ID: {case_id}")
logger.info(f"Stored file: {storage_key}")
logger.warning(f"File {filename} exceeds size limit, skipping")
logger.error(f"Failed to process ZIP file: {e}")
```

## Next Steps

After Stage 0 implementation:
1. **Stage 1**: Document Classification (classify uploaded files)
2. **Stage 2**: Data Extraction (OCR and field extraction)
3. **Stage 3**: Feature Assembly (build borrower profile)
4. **Stage 4**: Eligibility Scoring (match with lenders)
5. **Stage 5**: Report Generation (create submission packages)

## Troubleshooting

### Files not uploading
- Check file size limits in config
- Verify allowed extensions
- Check storage directory permissions

### Case ID conflicts
- Verify database connection
- Check case ID generation logic
- Ensure proper transaction handling

### ZIP extraction fails
- Validate ZIP file integrity
- Check for nested ZIPs (not supported)
- Verify extracted file sizes

## Contributing

When adding features to Stage 0:
1. Update models if schema changes
2. Add tests for new functionality
3. Update this README
4. Follow existing code patterns
5. Use proper error handling
6. Add appropriate logging

## License

Internal project - DSA Case OS
