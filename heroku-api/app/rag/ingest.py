"""
Document ingestion pipeline for RAG system
Downloads, processes, and stores compliance documents
"""

import os
import hashlib
from typing import List, Dict, Any
from datetime import datetime
import tempfile

import httpx
from pypdf import PdfReader
import structlog

from .splitter import RecursiveTextSplitter
from .embedder import Embedder
from .store import VectorStore

logger = structlog.get_logger()


async def ingest_document(
    source_url: str,
    document_id: str,
    document_title: str = None,
    document_type: str = "regulation",
    category: str = "compliance",
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Ingest a document into the RAG system.

    Args:
        source_url: URL to download document from (PDF)
        document_id: Unique document identifier
        document_title: Document title (default: use document_id)
        document_type: Type of document (regulation, policy, procedure)
        category: Category for filtering
        metadata: Additional metadata

    Returns:
        Dict with ingestion results
    """
    document_title = document_title or document_id
    metadata = metadata or {}

    logger.info(
        "ingest.starting",
        document_id=document_id,
        source_url=source_url,
    )

    # 1. Download document
    try:
        content = await _download_pdf(source_url)
    except Exception as e:
        logger.error("ingest.download_failed", document_id=document_id, error=str(e))
        raise

    # 2. Extract text from PDF
    try:
        text = _extract_text_from_pdf(content)
    except Exception as e:
        logger.error("ingest.extraction_failed", document_id=document_id, error=str(e))
        raise

    # 3. Split into chunks
    splitter = RecursiveTextSplitter()
    chunks = splitter.split_text(text)

    if not chunks:
        logger.warning("ingest.no_chunks", document_id=document_id)
        return {
            "document_id": document_id,
            "status": "failed",
            "reason": "no_chunks_generated",
            "chunks_added": 0,
        }

    # 4. Generate embeddings
    embedder = Embedder()
    embeddings = embedder.embed_texts(chunks, batch_size=32)

    # 5. Prepare chunks with metadata
    chunk_dicts = []
    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk_metadata = {
            "document_id": document_id,
            "document_title": document_title,
            "document_type": document_type,
            "category": category,
            "source": source_url,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "ingested_at": datetime.utcnow().isoformat(),
            **metadata,
        }

        chunk_dicts.append({
            "text": chunk_text,
            "embedding": embedding,
            "metadata": chunk_metadata,
        })

    # 6. Store in vector database
    vector_store = VectorStore()
    num_added = vector_store.add_chunks(chunk_dicts)

    logger.info(
        "ingest.complete",
        document_id=document_id,
        num_chunks=num_added,
        text_length=len(text),
    )

    return {
        "document_id": document_id,
        "document_title": document_title,
        "status": "success",
        "chunks_added": num_added,
        "total_characters": len(text),
        "source_url": source_url,
    }


async def _download_pdf(url: str) -> bytes:
    """
    Download PDF from URL.

    Args:
        url: PDF URL

    Returns:
        PDF content as bytes
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower():
            logger.warning(
                "ingest.unexpected_content_type",
                url=url,
                content_type=content_type,
            )

        return response.content


def _extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text from PDF bytes.

    Args:
        pdf_content: PDF file content

    Returns:
        Extracted text
    """
    # Write to temp file (pypdf requires file-like object)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_file.write(pdf_content)
        tmp_path = tmp_file.name

    try:
        reader = PdfReader(tmp_path)
        text_parts = []

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(
                    "ingest.page_extraction_failed",
                    page_num=page_num,
                    error=str(e),
                )
                continue

        full_text = "\n\n".join(text_parts)

        logger.debug(
            "ingest.text_extracted",
            num_pages=len(reader.pages),
            text_length=len(full_text),
        )

        return full_text

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def delete_document(document_id: str) -> Dict[str, Any]:
    """
    Delete all chunks for a document.

    Args:
        document_id: Document ID to delete

    Returns:
        Dict with deletion results
    """
    vector_store = VectorStore()
    num_deleted = vector_store.delete_by_document(document_id)

    logger.info(
        "ingest.document_deleted",
        document_id=document_id,
        chunks_deleted=num_deleted,
    )

    return {
        "document_id": document_id,
        "status": "deleted",
        "chunks_deleted": num_deleted,
    }


async def ingest_text(
    text: str,
    document_id: str,
    document_title: str = None,
    document_type: str = "policy",
    category: str = "compliance",
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Ingest plain text directly (no PDF download).

    Args:
        text: Text content to ingest
        document_id: Unique document identifier
        document_title: Document title
        document_type: Type of document
        category: Category for filtering
        metadata: Additional metadata

    Returns:
        Dict with ingestion results
    """
    document_title = document_title or document_id
    metadata = metadata or {}

    logger.info(
        "ingest.text_starting",
        document_id=document_id,
        text_length=len(text),
    )

    # 1. Split into chunks
    splitter = RecursiveTextSplitter()
    chunks = splitter.split_text(text)

    if not chunks:
        return {
            "document_id": document_id,
            "status": "failed",
            "reason": "no_chunks_generated",
            "chunks_added": 0,
        }

    # 2. Generate embeddings
    embedder = Embedder()
    embeddings = embedder.embed_texts(chunks, batch_size=32)

    # 3. Prepare chunks with metadata
    chunk_dicts = []
    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk_metadata = {
            "document_id": document_id,
            "document_title": document_title,
            "document_type": document_type,
            "category": category,
            "source": "direct_input",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "ingested_at": datetime.utcnow().isoformat(),
            **metadata,
        }

        chunk_dicts.append({
            "text": chunk_text,
            "embedding": embedding,
            "metadata": chunk_metadata,
        })

    # 4. Store in vector database
    vector_store = VectorStore()
    num_added = vector_store.add_chunks(chunk_dicts)

    logger.info(
        "ingest.text_complete",
        document_id=document_id,
        num_chunks=num_added,
    )

    return {
        "document_id": document_id,
        "document_title": document_title,
        "status": "success",
        "chunks_added": num_added,
        "total_characters": len(text),
    }