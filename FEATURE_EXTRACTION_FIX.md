# Feature Extraction Fix

## Problem Identified

Feature extraction fails because:
1. Some documents might not have OCR text (password-protected PDFs, failed OCR)
2. Extraction is not auto-triggered after upload
3. Bank statement analysis might be failing

## Solutions

### Fix 1: Make Extraction More Robust
- Don't fail if some documents don't have OCR
- Skip documents without OCR text
- Better error handling

### Fix 2: Auto-Trigger Extraction
- After document upload completes
- After OCR finishes
- Run in background

### Fix 3: Better Logging
- Show which documents succeeded
- Show which documents failed
- Give user feedback

## Files to Update

1. `backend/app/api/v1/endpoints/extraction.py` - Make more robust
2. `backend/app/services/stages/stage0_case_entry.py` - Auto-trigger extraction
3. Frontend - Better UI feedback

## Deployment

After fixes:
```bash
cd ~/Downloads/dsa-case-os/docker
docker compose restart backend
```
