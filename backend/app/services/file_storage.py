"""File storage service - abstract interface with local filesystem implementation."""
import os
import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileStorageBackend(ABC):
    """Abstract interface for file storage backends."""

    @abstractmethod
    async def store_file(
        self,
        file_data: BinaryIO,
        case_id: str,
        filename: str
    ) -> str:
        """
        Store a file and return its storage key.

        Args:
            file_data: Binary file data stream
            case_id: Case ID (used for organizing files)
            filename: Original filename

        Returns:
            storage_key: Unique key to retrieve the file later
        """
        pass

    @abstractmethod
    async def get_file(self, storage_key: str) -> Optional[bytes]:
        """
        Retrieve file data by storage key.

        Args:
            storage_key: The key returned from store_file

        Returns:
            File data as bytes, or None if not found
        """
        pass

    @abstractmethod
    async def delete_file(self, storage_key: str) -> bool:
        """
        Delete a file by storage key.

        Args:
            storage_key: The key returned from store_file

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def file_exists(self, storage_key: str) -> bool:
        """Check if a file exists."""
        pass

    @abstractmethod
    def get_file_path(self, storage_key: str) -> Optional[Path]:
        """Get the actual file path (for local storage)."""
        pass


class LocalFileStorage(FileStorageBackend):
    """Local filesystem implementation of file storage."""

    def __init__(self, base_path: str = None):
        """
        Initialize local file storage.

        Args:
            base_path: Base directory for file storage (default from config)
        """
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized local file storage at: {self.base_path}")

    async def store_file(
        self,
        file_data: BinaryIO,
        case_id: str,
        filename: str
    ) -> str:
        """
        Store a file in the local filesystem.

        Storage structure: {base_path}/{case_id}/{filename}

        Args:
            file_data: Binary file data stream
            case_id: Case ID (used for directory organization)
            filename: Original filename

        Returns:
            storage_key: Relative path from base_path
        """
        # Create case-specific directory
        case_dir = self.base_path / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        # Build file path
        file_path = case_dir / filename

        # Handle duplicate filenames by appending counter
        counter = 1
        original_stem = file_path.stem
        original_suffix = file_path.suffix
        while file_path.exists():
            file_path = case_dir / f"{original_stem}_{counter}{original_suffix}"
            counter += 1

        # Write file
        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file_data, f)

            # Return storage key (relative path from base)
            storage_key = str(file_path.relative_to(self.base_path))
            logger.info(f"Stored file: {storage_key}")
            return storage_key

        except Exception as e:
            logger.error(f"Failed to store file {filename}: {e}")
            raise

    async def get_file(self, storage_key: str) -> Optional[bytes]:
        """Retrieve file data by storage key."""
        file_path = self.base_path / storage_key

        if not file_path.exists():
            logger.warning(f"File not found: {storage_key}")
            return None

        try:
            with open(file_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read file {storage_key}: {e}")
            raise

    async def delete_file(self, storage_key: str) -> bool:
        """Delete a file by storage key."""
        file_path = self.base_path / storage_key

        if not file_path.exists():
            logger.warning(f"File not found for deletion: {storage_key}")
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted file: {storage_key}")

            # Clean up empty directories
            try:
                file_path.parent.rmdir()
            except OSError:
                # Directory not empty, that's fine
                pass

            return True
        except Exception as e:
            logger.error(f"Failed to delete file {storage_key}: {e}")
            raise

    async def file_exists(self, storage_key: str) -> bool:
        """Check if a file exists."""
        file_path = self.base_path / storage_key
        return file_path.exists()

    def get_file_path(self, storage_key: str) -> Optional[Path]:
        """Get the actual file path."""
        file_path = self.base_path / storage_key
        return file_path if file_path.exists() else None


class S3FileStorage(FileStorageBackend):
    """S3 implementation - placeholder for future implementation."""

    def __init__(self, bucket: str, region: str = "us-east-1"):
        self.bucket = bucket
        self.region = region
        logger.info(f"Initialized S3 file storage (bucket: {bucket})")

    async def store_file(self, file_data: BinaryIO, case_id: str, filename: str) -> str:
        raise NotImplementedError("S3 storage not yet implemented")

    async def get_file(self, storage_key: str) -> Optional[bytes]:
        raise NotImplementedError("S3 storage not yet implemented")

    async def delete_file(self, storage_key: str) -> bool:
        raise NotImplementedError("S3 storage not yet implemented")

    async def file_exists(self, storage_key: str) -> bool:
        raise NotImplementedError("S3 storage not yet implemented")

    def get_file_path(self, storage_key: str) -> Optional[Path]:
        return None  # S3 doesn't use local paths


def get_storage_backend() -> FileStorageBackend:
    """
    Factory function to get the configured storage backend.

    Returns:
        FileStorageBackend: Configured storage backend instance
    """
    if settings.STORAGE_BACKEND == "s3":
        if not settings.S3_BUCKET:
            raise ValueError("S3_BUCKET must be configured for S3 storage")
        return S3FileStorage(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION or "us-east-1"
        )
    else:
        return LocalFileStorage(settings.LOCAL_STORAGE_PATH)


def compute_file_hash(file_data: BinaryIO) -> str:
    """
    Compute SHA-256 hash of file data.

    Args:
        file_data: Binary file data stream

    Returns:
        Hexadecimal hash string
    """
    hasher = hashlib.sha256()

    # Read file in chunks to handle large files
    file_data.seek(0)  # Reset to beginning
    while chunk := file_data.read(8192):
        hasher.update(chunk)

    file_data.seek(0)  # Reset for future reads
    return hasher.hexdigest()
