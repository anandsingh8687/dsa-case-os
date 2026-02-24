"""RAG ingestion and retrieval service for lender policy documents."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import math
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from uuid import UUID

import fitz  # PyMuPDF
from openai import AsyncOpenAI
try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency at runtime
    SentenceTransformer = None

from app.core.config import settings
from app.db.database import get_asyncpg_pool

logger = logging.getLogger(__name__)

DEFAULT_POLICY_SOURCES = [
    "/Users/aparajitasharma/Downloads/ILB((POLICY PINCODE)-20260222T040809Z-1-001.zip",
    "/Users/aparajitasharma/Downloads/Policies BL -20260222T040706Z-1-001.zip",
]

SUPPORTED_DOC_EXTENSIONS = {".pdf", ".txt", ".md"}
_EMBED_MODEL: SentenceTransformer | None = None
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_/\\-]*")
_EMBED_DIM = 384
KNOWN_LENDER_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("Aditya Birla Finance", ("aditya birla", "abfl")),
    ("Arthmate", ("arthmate",)),
    ("Ambit", ("ambit",)),
    ("Bajaj", ("bajaj",)),
    ("Clix Capital", ("clix",)),
    ("Credit Saison", ("credit saison", "saison")),
    ("Flexiloans", ("flexiloans", "flexi loans")),
    ("Godrej Capital", ("godrej",)),
    ("HDFC", ("hdfc",)),
    ("IDFC First Bank", ("idfc", "idfc first")),
    ("ICICI", ("icici",)),
    ("SBI", ("sbi", "state bank of india")),
    ("InCred", ("incred",)),
    ("IIFL", ("iifl",)),
    ("Indifi", ("indifi",)),
    ("KreditBee", ("kreditbee", "kredit bee")),
    ("Moneyview", ("moneyview", "money view")),
    ("Muthoot Finance", ("muthoot",)),
    ("Prefr", ("prefr",)),
    ("Fibe", ("fibe",)),
    ("TruCap", ("trucap", "tru cap")),
    ("Lendingkart", ("lendingkart",)),
    ("NeoGrowth", ("neogrowth", "neo growth")),
    ("Protium", ("protium",)),
    ("Tata Capital", ("tata capital", "tata")),
]
KNOWN_PRODUCT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("Working Capital", ("working capital", "wc")),
    ("Home Loan", ("home loan", "hl", "htbl")),
    ("Personal Loan", ("personal loan", "pl")),
    ("Loan Against Property", ("loan against property", "lap")),
    ("Business Loan", ("business loan", "bl", "stbl", "mtbl", "od", "sbl")),
]


@dataclass
class DocumentChunk:
    lender_name: str
    product_type: str
    section_title: str
    chunk_text: str
    source_file: str


def _get_embed_model() -> SentenceTransformer | None:
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        if SentenceTransformer is None:
            logger.warning(
                "sentence-transformers not installed; using local hashed embeddings fallback (dim=%s).",
                _EMBED_DIM,
            )
            return None
        _EMBED_MODEL = SentenceTransformer(settings.RAG_EMBEDDING_MODEL)
    return _EMBED_MODEL


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm <= 0:
        return values
    return [v / norm for v in values]


def _hash_embed_text(text: str, dim: int = _EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text.lower())
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], byteorder="big", signed=False) % dim
        sign = -1.0 if (digest[4] & 1) else 1.0
        # Keep contribution bounded across long chunks.
        vec[idx] += sign * (1.0 / max(1, len(tokens)))

    return _normalize_vector(vec)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embed_model()
    if model is not None:
        return model.encode(texts, normalize_embeddings=True).tolist()
    return [_hash_embed_text(text) for text in texts]


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def _chunk_text_by_tokens(text: str, min_tokens: int = 500, max_tokens: int = 800, overlap: int = 100) -> list[str]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    chunks: list[str] = []
    start = 0
    step = max(min_tokens, max_tokens - overlap)
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        window = tokens[start:end]
        if len(window) >= min_tokens or (start == 0 and end == len(tokens)):
            chunks.append(" ".join(window))
        start += step
    return chunks


def _guess_lender_name(text: str) -> str | None:
    haystack = f" {text.lower()} "
    for lender_name, aliases in KNOWN_LENDER_PATTERNS:
        for alias in aliases:
            if f" {alias} " in haystack or alias in haystack:
                return lender_name
    return None


def _guess_product_type(text: str) -> str | None:
    haystack = f" {text.lower()} "
    for product_name, aliases in KNOWN_PRODUCT_PATTERNS:
        for alias in aliases:
            if f" {alias} " in haystack or alias in haystack:
                return product_name
    return None


def _looks_like_invalid_lender_name(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return True
    letters = re.sub(r"[^A-Za-z]", "", normalized)
    return len(letters) < 3


def _extract_pdf_text(path: Path) -> str:
    text_parts: list[str] = []
    doc = fitz.open(path)
    try:
        for page in doc:
            text_parts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n".join(text_parts).strip()


async def _infer_lender_product(filename: str, context_text: str) -> tuple[str, str]:
    base = Path(filename).stem.replace("_", " ").replace("-", " ")
    context_window = f"{base} {context_text[:6000]}"
    guessed_lender = _guess_lender_name(context_window)
    guessed_product = _guess_product_type(context_window)
    tokens = [t for t in base.split() if t]
    fallback_lender = guessed_lender or (tokens[0].title() if tokens else "Unknown Lender")
    fallback_product = guessed_product or "Business Loan"

    # Simple filename heuristics first.
    lower = base.lower()
    filename_lower = filename.lower()
    if "home" in lower or "hl" in lower:
        fallback_product = "Home Loan"
    elif "personal" in lower or "pl" in lower:
        fallback_product = "Personal Loan"
    elif "working capital" in lower or "wc" in lower:
        fallback_product = "Working Capital"
    elif "bl" in lower or "business" in lower:
        fallback_product = "Business Loan"
    elif "policies bl" in filename_lower or "/bl" in filename_lower or "\\bl" in filename_lower:
        fallback_product = "Business Loan"

    if not settings.LLM_API_KEY:
        return fallback_lender, fallback_product

    prompt = (
        "Identify lender_name and product_type from this document metadata. "
        "Return strict JSON: {\"lender_name\":\"...\",\"product_type\":\"...\"}. "
        "Use concise values (example: Bajaj Finance, Business Loan). "
        f"Filename: {filename}\n"
        f"Content sample: {context_text[:1500]}"
    )

    def _extract_json_object(raw_text: str) -> dict:
        cleaned = (raw_text or "").strip()
        if not cleaned:
            return {}

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            return json.loads(cleaned)
        except Exception:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                return {}
        return {}

    try:
        client = AsyncOpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
        response = await client.chat.completions.create(
            model=settings.COPILOT_FAST_MODEL or settings.LLM_MODEL,
            temperature=0.1,
            max_tokens=120,
            messages=[
                {"role": "system", "content": "You extract structured lender metadata from loan policy docs."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        parsed = _extract_json_object(raw)
        lender_name = (parsed.get("lender_name") or fallback_lender).strip()
        product_type = (parsed.get("product_type") or fallback_product).strip()
        if _looks_like_invalid_lender_name(lender_name):
            lender_name = guessed_lender or fallback_lender
        guessed_final_product = _guess_product_type(f"{product_type} {base} {context_text[:2000]}")
        if guessed_final_product:
            product_type = guessed_final_product
        return lender_name, product_type
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM metadata inference failed for %s: %s", filename, exc)
        return fallback_lender, fallback_product


def _embedding_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    n = min(len(a), len(b))
    if n <= 0:
        return 1.0
    dot = sum(a[i] * b[i] for i in range(n))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if norm_a <= 0 or norm_b <= 0:
        return 1.0
    cosine = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
    return 1.0 - cosine


def _parse_embedding_json(raw: str | None) -> list[float]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [float(v) for v in parsed]
    except Exception:
        return []
    return []


async def _rag_capabilities(db) -> tuple[bool, bool]:
    row = await db.fetchrow(
        """
        SELECT
          EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'lender_documents'
          ) AS has_table,
          EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'lender_documents'
              AND column_name = 'embedding'
          ) AS has_vector_column
        """
    )
    if not row:
        return False, False
    return bool(row["has_table"]), bool(row["has_vector_column"])


async def search_relevant_lender_chunks(
    *,
    organization_id: UUID,
    query: str,
    top_k: int | None = None,
) -> list[dict]:
    if not query.strip():
        return []

    top = top_k or settings.RAG_TOP_K
    query_vector = _embed_texts([query])[0]

    try:
        pool = await get_asyncpg_pool()
        async with pool.acquire() as db:
            has_table, has_vector_column = await _rag_capabilities(db)
            if not has_table:
                return []

            if has_vector_column:
                vector_text = _embedding_literal(query_vector)
                rows = await db.fetch(
                    """
                    SELECT lender_name, product_type, section_title, chunk_text, source_file,
                           (embedding <=> $2::vector) AS distance
                    FROM lender_documents
                    WHERE organization_id = $1
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    organization_id,
                    vector_text,
                    top,
                )
                return [dict(row) for row in rows]

            # Fallback path for environments without pgvector support.
            rows = await db.fetch(
                """
                SELECT lender_name, product_type, section_title, chunk_text, source_file, embedding_json
                FROM lender_documents
                WHERE organization_id = $1
                LIMIT 2000
                """,
                organization_id,
            )

        scored: list[dict] = []
        for row in rows:
            row_dict = dict(row)
            embedding = _parse_embedding_json(row_dict.get("embedding_json"))
            if not embedding:
                continue
            distance = _cosine_distance(query_vector, embedding)
            scored.append(
                {
                    "lender_name": row_dict.get("lender_name"),
                    "product_type": row_dict.get("product_type"),
                    "section_title": row_dict.get("section_title"),
                    "chunk_text": row_dict.get("chunk_text"),
                    "source_file": row_dict.get("source_file"),
                    "distance": distance,
                }
            )
        scored.sort(key=lambda item: item["distance"])
        return scored[:top]
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG search unavailable for org %s: %s", organization_id, exc)
        return []


def _iter_policy_candidate_files(base_paths: Iterable[str]) -> list[Path]:
    """Collect policy files from explicit ZIPs/folders only.

    Important: this intentionally avoids sweeping entire parent folders
    (for example ~/Downloads) to prevent accidental ingestion of unrelated docs.
    """
    candidates: set[Path] = set()

    for raw_path in base_paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            logger.warning("RAG source path does not exist: %s", path)
            continue

        if path.is_file() and path.suffix.lower() == ".zip":
            candidates.add(path)
            extracted_dir = path.with_suffix("")
            if extracted_dir.exists() and extracted_dir.is_dir():
                for file in extracted_dir.rglob("*"):
                    if file.is_file() and file.suffix.lower() in SUPPORTED_DOC_EXTENSIONS | {".zip"}:
                        candidates.add(file)
        elif path.is_dir():
            for file in path.rglob("*"):
                if file.is_file() and file.suffix.lower() in SUPPORTED_DOC_EXTENSIONS | {".zip"}:
                    candidates.add(file)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            candidates.add(path)

    return sorted(candidates)


async def _ingest_file_content(
    *,
    organization_id: UUID,
    source_file: Path,
    text: str,
    db,
    has_vector_column: bool,
) -> int:
    if not text.strip():
        return 0

    lender_name, product_type = await _infer_lender_product(str(source_file), text[:2000])
    chunks = _chunk_text_by_tokens(text)
    if not chunks:
        return 0

    embeddings = _embed_texts(chunks)

    inserted = 0
    for idx, (chunk_text, vector) in enumerate(zip(chunks, embeddings), start=1):
        section_title = f"{source_file.stem} - chunk {idx}"
        vector_literal = _embedding_literal(vector)
        vector_json = json.dumps(vector)
        existing_id = await db.fetchval(
            """
            SELECT id
            FROM lender_documents
            WHERE organization_id = $1
              AND LOWER(lender_name) = LOWER($2)
              AND LOWER(product_type) = LOWER($3)
              AND COALESCE(section_title, '') = COALESCE($4, '')
            LIMIT 1
            """,
            organization_id,
            lender_name,
            product_type,
            section_title,
        )

        if existing_id:
            if has_vector_column:
                await db.execute(
                    """
                    UPDATE lender_documents
                    SET chunk_text = $2,
                        embedding = $3::vector,
                        embedding_json = $4,
                        source_file = $5,
                        last_updated = NOW()
                    WHERE id = $1
                    """,
                    existing_id,
                    chunk_text,
                    vector_literal,
                    vector_json,
                    str(source_file),
                )
            else:
                await db.execute(
                    """
                    UPDATE lender_documents
                    SET chunk_text = $2,
                        embedding_json = $3,
                        source_file = $4,
                        last_updated = NOW()
                    WHERE id = $1
                    """,
                    existing_id,
                    chunk_text,
                    vector_json,
                    str(source_file),
                )
        else:
            if has_vector_column:
                await db.execute(
                    """
                    INSERT INTO lender_documents (
                        organization_id, lender_name, product_type, section_title, chunk_text, embedding, embedding_json, source_file, last_updated
                    )
                    VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, NOW())
                    """,
                    organization_id,
                    lender_name,
                    product_type,
                    section_title,
                    chunk_text,
                    vector_literal,
                    vector_json,
                    str(source_file),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO lender_documents (
                        organization_id, lender_name, product_type, section_title, chunk_text, embedding_json, source_file, last_updated
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                    """,
                    organization_id,
                    lender_name,
                    product_type,
                    section_title,
                    chunk_text,
                    vector_json,
                    str(source_file),
                )
            inserted += 1
    return inserted


async def ingest_lender_policy_documents(
    *,
    organization_id: UUID,
    source_paths: Optional[list[str]] = None,
) -> dict:
    """Ingest lender policy docs from ZIP/folders into pgvector table."""
    paths = source_paths or DEFAULT_POLICY_SOURCES
    candidates = _iter_policy_candidate_files(paths)

    processed_files = 0
    inserted_chunks = 0
    skipped_files = 0

    pool = await get_asyncpg_pool()
    async with pool.acquire() as db:
        has_table, has_vector_column = await _rag_capabilities(db)
    if not has_table:
        return {
            "organization_id": str(organization_id),
            "candidate_files": len(candidates),
            "processed_files": 0,
            "inserted_chunks": 0,
            "skipped_files": len(candidates),
            "source_paths": paths,
            "status": "skipped",
            "reason": "lender_documents table is unavailable",
            "ingested_at": datetime.utcnow().isoformat() + "Z",
        }

    for source in candidates:
        try:
            if source.suffix.lower() == ".zip":
                with zipfile.ZipFile(source, "r") as zf:
                    with tempfile.TemporaryDirectory(prefix="rag_ingest_") as td:
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            member_name = Path(member.filename).name
                            if not member_name:
                                continue
                            member_suffix = Path(member_name).suffix.lower()
                            if member_suffix not in SUPPORTED_DOC_EXTENSIONS:
                                continue

                            extracted_file = Path(td) / member_name
                            with zf.open(member) as src, extracted_file.open("wb") as dst:
                                dst.write(src.read())

                            text = (
                                _extract_pdf_text(extracted_file)
                                if member_suffix == ".pdf"
                                else extracted_file.read_text(
                                encoding="utf-8", errors="ignore"
                                )
                            )
                            async with pool.acquire() as db:
                                inserted_chunks += await _ingest_file_content(
                                    organization_id=organization_id,
                                    source_file=Path(f"{source.name}:{member.filename}"),
                                    text=text,
                                    db=db,
                                    has_vector_column=has_vector_column,
                                )
                            processed_files += 1
            elif source.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
                text = _extract_pdf_text(source) if source.suffix.lower() == ".pdf" else source.read_text(
                    encoding="utf-8", errors="ignore"
                )
                async with pool.acquire() as db:
                    inserted_chunks += await _ingest_file_content(
                        organization_id=organization_id,
                        source_file=source,
                        text=text,
                        db=db,
                        has_vector_column=has_vector_column,
                    )
                processed_files += 1
            else:
                skipped_files += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to ingest %s: %s", source, exc)
            skipped_files += 1

    return {
        "organization_id": str(organization_id),
        "candidate_files": len(candidates),
        "processed_files": processed_files,
        "inserted_chunks": inserted_chunks,
        "skipped_files": skipped_files,
        "source_paths": paths,
        "ingested_at": datetime.utcnow().isoformat() + "Z",
    }
