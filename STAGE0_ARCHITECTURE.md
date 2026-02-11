# Stage 0 Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         DSA Case OS                              │
│                   Stage 0: Case Entry Module                     │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐
│   Client     │  (Web App / Mobile / API Consumer)
└──────┬───────┘
       │ HTTP/HTTPS
       │
┌──────▼───────────────────────────────────────────────────────────┐
│                      FastAPI Application                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              API Endpoints (cases.py)                       │ │
│  │  • POST /cases/          - Create case                      │ │
│  │  • POST /cases/{id}/upload - Upload files                   │ │
│  │  • GET /cases/           - List cases                       │ │
│  │  • GET /cases/{id}       - Get case                         │ │
│  │  • PATCH /cases/{id}     - Update case                      │ │
│  │  • DELETE /cases/{id}    - Delete case                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                             │                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         Business Logic (CaseEntryService)                   │ │
│  │  • Case management (CRUD)                                   │ │
│  │  • File upload handling                                     │ │
│  │  • ZIP extraction                                           │ │
│  │  • Duplicate detection                                      │ │
│  │  • Validation & error handling                              │ │
│  └─────┬──────────────────────────────────┬───────────────────┘ │
│        │                                   │                     │
│   ┌────▼────────┐                   ┌─────▼──────────┐         │
│   │ File Storage│                   │  Database      │         │
│   │   Service   │                   │  (PostgreSQL)  │         │
│   │             │                   │                │         │
│   │ • Local FS  │                   │ • Cases        │         │
│   │ • S3 Ready  │                   │ • Documents    │         │
│   └─────────────┘                   └────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Create Case Flow

```
Client                FastAPI               Service              Database
  │                     │                      │                    │
  │ POST /cases/        │                      │                    │
  ├────────────────────>│                      │                    │
  │  {borrower_name}    │  create_case()       │                    │
  │                     ├─────────────────────>│                    │
  │                     │                      │ generate_case_id() │
  │                     │                      ├───────────────────>│
  │                     │                      │  SELECT MAX(...)   │
  │                     │                      │<───────────────────┤
  │                     │                      │  CASE-20240210-0001│
  │                     │                      │                    │
  │                     │                      │  INSERT case       │
  │                     │                      ├───────────────────>│
  │                     │                      │<───────────────────┤
  │                     │  CaseResponse        │      Success       │
  │                     │<─────────────────────┤                    │
  │  201 Created        │                      │                    │
  │<────────────────────┤                      │                    │
  │  {case_id: ...}     │                      │                    │
```

### 2. File Upload Flow

```
Client          FastAPI         Service         Storage         Database
  │               │               │               │               │
  │ POST /upload  │               │               │               │
  ├──────────────>│               │               │               │
  │  files[]      │ upload_files()│               │               │
  │               ├──────────────>│               │               │
  │               │               │               │               │
  │               │               │ Validate size │               │
  │               │               │ & extension   │               │
  │               │               │               │               │
  │               │               │ Compute hash  │               │
  │               │               │ (SHA-256)     │               │
  │               │               │               │               │
  │               │               │ Check duplicate               │
  │               │               ├──────────────────────────────>│
  │               │               │ SELECT WHERE hash=?           │
  │               │               │<──────────────────────────────┤
  │               │               │               │               │
  │               │               │ Store file    │               │
  │               │               ├──────────────>│               │
  │               │               │               │ Write to disk │
  │               │               │<──────────────┤               │
  │               │               │ storage_key   │               │
  │               │               │               │               │
  │               │               │ INSERT document               │
  │               │               ├──────────────────────────────>│
  │               │               │<──────────────────────────────┤
  │               │               │               │               │
  │               │ DocumentResponse[]            │               │
  │               │<──────────────┤               │               │
  │ 200 OK        │               │               │               │
  │<──────────────┤               │               │               │
  │ [{id,...}]    │               │               │               │
```

### 3. ZIP Processing Flow

```
                ┌─────────────────────────────────────┐
                │     ZIP File Uploaded               │
                └────────────┬────────────────────────┘
                             │
                             ▼
                ┌─────────────────────────────────────┐
                │  Extract ZIP Archive                │
                │  (using Python zipfile)             │
                └────────────┬────────────────────────┘
                             │
                             ▼
                ┌─────────────────────────────────────┐
                │  For each file in ZIP:              │
                └────────────┬────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│ Skip if     │    │ Flatten folder  │    │ Validate    │
│ ignored:    │    │ structure       │    │ extension   │
│ .DS_Store   │    │ /sub/file.pdf   │    │ & size      │
│ __MACOSX    │    │ → file.pdf      │    │             │
└─────────────┘    └─────────┬───────┘    └──────┬──────┘
                             │                    │
                             └──────┬─────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │  Process as individual file  │
                     │  (same as single upload)     │
                     └──────────────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │  Store + Create DB record    │
                     └──────────────────────────────┘
```

## Component Architecture

### Layer Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FastAPI Endpoints (cases.py)                            │   │
│  │  • Request validation (Pydantic)                         │   │
│  │  • Response serialization                                │   │
│  │  • HTTP status codes                                     │   │
│  │  • Authentication (placeholder)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Business Logic Layer                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CaseEntryService (stage0_case_entry.py)                │   │
│  │  • Case CRUD operations                                  │   │
│  │  • File upload orchestration                             │   │
│  │  • ZIP extraction logic                                  │   │
│  │  • Duplicate detection                                   │   │
│  │  • Business rule validation                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Utilities                                               │   │
│  │  • Case ID Generator (case_id_generator.py)             │   │
│  │  • File hash computation                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Data Access Layer                             │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │  File Storage            │  │  Database (SQLAlchemy)   │    │
│  │  (file_storage.py)       │  │  (models/case.py)        │    │
│  │  • Abstract interface    │  │  • Case model            │    │
│  │  • Local implementation  │  │  • Document model        │    │
│  │  • S3 stub               │  │  • Async queries         │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                          │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │  File System             │  │  PostgreSQL Database     │    │
│  │  ./uploads/              │  │  dsa_case_os             │    │
│  │  ├─ CASE-xxx-0001/       │  │  ├─ cases table         │    │
│  │  │  ├─ file1.pdf         │  │  └─ documents table     │    │
│  │  │  └─ file2.jpg         │  │                          │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Models                                   │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│      Case            │
├──────────────────────┤
│ id: UUID             │
│ case_id: str         │◄────────┐
│ user_id: UUID        │         │
│ status: str          │         │  One-to-Many
│ borrower_name: str   │         │
│ entity_type: str     │         │
│ program_type: str    │         │
│ ...                  │         │
│ created_at: datetime │         │
│ updated_at: datetime │         │
└──────────────────────┘         │
                                 │
                      ┌──────────┴───────────┐
                      │     Document         │
                      ├──────────────────────┤
                      │ id: UUID             │
                      │ case_id: UUID (FK)   │
                      │ original_filename    │
                      │ storage_key          │
                      │ file_size_bytes      │
                      │ mime_type            │
                      │ file_hash            │
                      │ doc_type             │
                      │ status               │
                      │ created_at           │
                      └──────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         Services                                 │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────────────┐
│   CaseEntryService         │
├────────────────────────────┤
│ - db: AsyncSession         │
│ - storage: StorageBackend  │
├────────────────────────────┤
│ + create_case()            │
│ + upload_files()           │
│ + get_case()               │
│ + list_cases()             │
│ + update_case()            │
│ + delete_case()            │
│ - _process_single_file()   │
│ - _process_zip_file()      │
│ - _find_duplicate()        │
└────────────────────────────┘
            │
            │ uses
            ▼
┌────────────────────────────┐
│  FileStorageBackend        │ (Abstract)
├────────────────────────────┤
│ + store_file()             │
│ + get_file()               │
│ + delete_file()            │
│ + file_exists()            │
└────────────────────────────┘
            △
            │ implements
            │
    ┌───────┴────────┐
    │                │
┌───▼───────┐  ┌────▼─────┐
│LocalFile  │  │ S3File   │
│Storage    │  │ Storage  │
└───────────┘  └──────────┘
```

## Database Schema

```sql
┌─────────────────────────────────────────────────────────────┐
│                         cases                                │
├────────────────┬────────────────────────────────────────────┤
│ id             │ UUID PRIMARY KEY                           │
│ case_id        │ VARCHAR(20) UNIQUE NOT NULL               │
│ user_id        │ UUID NOT NULL                             │
│ status         │ VARCHAR(30) DEFAULT 'created'             │
│ program_type   │ VARCHAR(10)                               │
│ borrower_name  │ VARCHAR(255)                              │
│ entity_type    │ VARCHAR(20)                               │
│ ...            │ (other fields)                            │
│ created_at     │ TIMESTAMPTZ DEFAULT NOW()                 │
│ updated_at     │ TIMESTAMPTZ DEFAULT NOW()                 │
└────────────────┴────────────────────────────────────────────┘
        │
        │ CASCADE DELETE
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                      documents                               │
├────────────────┬────────────────────────────────────────────┤
│ id             │ UUID PRIMARY KEY                           │
│ case_id        │ UUID REFERENCES cases(id) ON DELETE CASCADE│
│ original_name  │ VARCHAR(512)                               │
│ storage_key    │ VARCHAR(512) NOT NULL                      │
│ file_size_bytes│ BIGINT                                     │
│ mime_type      │ VARCHAR(100)                               │
│ file_hash      │ VARCHAR(64)  -- SHA-256 for dedup         │
│ doc_type       │ VARCHAR(30) DEFAULT 'unknown'             │
│ status         │ VARCHAR(20) DEFAULT 'uploaded'            │
│ ocr_text       │ TEXT                                       │
│ page_count     │ INTEGER                                    │
│ created_at     │ TIMESTAMPTZ DEFAULT NOW()                 │
└────────────────┴────────────────────────────────────────────┘

Indexes:
- cases.case_id (UNIQUE)
- cases.user_id
- cases.status
- documents.case_id
- documents.file_hash (for duplicate detection)
```

## File Storage Structure

```
uploads/
├── CASE-20240210-0001/
│   ├── pan_card.pdf
│   ├── aadhaar.jpg
│   ├── bank_statement.pdf
│   └── gst_certificate.pdf
├── CASE-20240210-0002/
│   ├── document1.pdf
│   ├── document2.pdf
│   └── image.png
└── CASE-20240210-0003/
    └── ...

Storage Keys in DB:
- CASE-20240210-0001/pan_card.pdf
- CASE-20240210-0001/aadhaar.jpg
- etc.
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Security Layers                            │
└─────────────────────────────────────────────────────────────┘

1. Input Validation
   ├─ File size limits (25MB/file, 100MB/case)
   ├─ Extension whitelist (pdf, jpg, jpeg, png, tiff, zip)
   ├─ MIME type validation
   └─ Path traversal prevention

2. Authentication (Placeholder)
   ├─ JWT token validation (to be implemented)
   └─ User ID extraction

3. Authorization
   ├─ User can only access own cases
   └─ Case ownership verification on all operations

4. Data Integrity
   ├─ SHA-256 hash for duplicate detection
   ├─ Database constraints (foreign keys, unique)
   └─ Transaction management

5. Error Handling
   ├─ Graceful degradation
   ├─ Proper HTTP status codes
   ├─ Detailed logging
   └─ No sensitive data in errors
```

## Scalability Considerations

```
Current Implementation (MVP):
- Single server
- Local file storage
- PostgreSQL database
- Synchronous file processing

Future Scaling Path:

1. Storage
   Local FS → S3/Cloud Storage
   (Already architected, just implement S3FileStorage)

2. Processing
   Sync → Async (Celery/RQ)
   - Background file processing
   - ZIP extraction in workers
   - OCR in separate queue

3. Database
   Single instance → Replicas
   - Read replicas for queries
   - Write to primary

4. Caching
   Add Redis for:
   - Session storage
   - Case metadata
   - Recently accessed files

5. Load Balancing
   Single server → Multiple servers
   - Nginx/HAProxy
   - Sticky sessions
   - Shared file storage (S3)
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Handling                            │
└─────────────────────────────────────────────────────────────┘

Exception Type              HTTP Code    Action
─────────────────────────────────────────────────────────────
File too large              413          Skip file, log warning
Unsupported extension       (skip)       Skip file, log warning
Invalid ZIP                 400          Return error to client
Case not found              404          Return error to client
Duplicate file              (skip)       Skip, log info
Database error              500          Rollback, return error
Storage error               500          Rollback, return error
Validation error            422          Return validation details

All errors are logged with:
- Timestamp
- User ID
- Case ID (if applicable)
- Full stack trace
- Request context
```

---

This architecture provides a solid foundation for Stage 0 while being ready to scale and integrate with future stages.
