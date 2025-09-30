"""
Hybrid retrieval combining vector search and BM25 keyword search
Uses Reciprocal Rank Fusion for result merging
"""

import os
from typing import List, Dict, Any

from rank_bm25 import BM25Okapi
import structlog

from .embedder import Embedder
from .store import VectorStore

logger = structlog.get_logger()

# Global instances (initialized on first use)
_embedder: Embedder = None
_vector_store: VectorStore = None


def _get_embedder() -> Embedder:
    """Get or create embedder singleton"""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_vector_store() -> VectorStore:
    """Get or create vector store singleton"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def hybrid_retrieve(
    query: str,
    top_k: int = None,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
    filters: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant chunks using hybrid search (vector + BM25).
    Uses Reciprocal Rank Fusion to combine results.

    Args:
        query: Search query
        top_k: Number of results to return (default from env)
        vector_weight: Weight for vector search results (0-1)
        bm25_weight: Weight for BM25 keyword results (0-1)
        filters: Optional metadata filters

    Returns:
        List of relevant chunks with combined scores
    """
    top_k = top_k or int(os.getenv("TOP_K_RAG", "5"))

    # Get embedder and vector store
    embedder = _get_embedder()
    vector_store = _get_vector_store()

    # 1. Vector similarity search
    query_embedding = embedder.embed_query(query)
    vector_results = vector_store.search(
        query_embedding=query_embedding,
        top_k=top_k * 2,  # Get more for fusion
        filters=filters,
    )

    logger.debug(
        "retriever.vector_search_complete",
        num_results=len(vector_results),
    )

    # 2. BM25 keyword search (fallback if vector search fails or has few results)
    bm25_results = []
    if len(vector_results) < top_k:
        bm25_results = _bm25_search(query, vector_store, top_k * 2, filters)
        logger.debug(
            "retriever.bm25_search_complete",
            num_results=len(bm25_results),
        )

    # 3. Reciprocal Rank Fusion
    if bm25_results:
        fused_results = _reciprocal_rank_fusion(
            vector_results,
            bm25_results,
            vector_weight,
            bm25_weight,
        )
    else:
        fused_results = vector_results

    # 4. Return top K
    final_results = fused_results[:top_k]

    logger.info(
        "retriever.hybrid_retrieve_complete",
        query_length=len(query),
        num_results=len(final_results),
        top_k=top_k,
    )

    return final_results


def _bm25_search(
    query: str,
    vector_store: VectorStore,
    top_k: int,
    filters: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    Perform BM25 keyword search.

    Args:
        query: Search query
        vector_store: Vector store to search
        top_k: Number of results
        filters: Optional metadata filters

    Returns:
        List of matching chunks
    """
    # Get all chunks (or filtered subset)
    # Note: In production, maintain a separate BM25 index
    # For now, we use vector search with wildcard and filter by keyword match

    # Tokenize query
    query_tokens = query.lower().split()

    # Simple keyword matching fallback
    # In production, maintain proper BM25 index in Redis or separate service
    results = vector_store.search(
        query_embedding=[0.0] * vector_store.embed_dim,  # Dummy vector
        top_k=top_k * 3,
        filters=filters,
    )

    # Score by keyword overlap
    scored_results = []
    for result in results:
        text_tokens = result["text"].lower().split()
        overlap = len(set(query_tokens) & set(text_tokens))
        if overlap > 0:
            result["score"] = overlap / len(query_tokens)
            scored_results.append(result)

    # Sort by score
    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:top_k]


def _reciprocal_rank_fusion(
    results_a: List[Dict[str, Any]],
    results_b: List[Dict[str, Any]],
    weight_a: float = 0.7,
    weight_b: float = 0.3,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Combine two result lists using Reciprocal Rank Fusion.

    RRF formula: score = weight * (1 / (k + rank))

    Args:
        results_a: First result list (e.g., vector search)
        results_b: Second result list (e.g., BM25)
        weight_a: Weight for first list
        weight_b: Weight for second list
        k: Constant for RRF (default 60)

    Returns:
        Fused and sorted results
    """
    # Build document ID to result mapping
    doc_map = {}

    # Add results from A
    for rank, result in enumerate(results_a, start=1):
        doc_id = result.get("document_id", "") + str(result.get("chunk_index", 0))
        rrf_score = weight_a * (1.0 / (k + rank))

        if doc_id not in doc_map:
            doc_map[doc_id] = {**result, "rrf_score": 0.0}

        doc_map[doc_id]["rrf_score"] += rrf_score

    # Add results from B
    for rank, result in enumerate(results_b, start=1):
        doc_id = result.get("document_id", "") + str(result.get("chunk_index", 0))
        rrf_score = weight_b * (1.0 / (k + rank))

        if doc_id not in doc_map:
            doc_map[doc_id] = {**result, "rrf_score": 0.0}

        doc_map[doc_id]["rrf_score"] += rrf_score

    # Sort by RRF score
    fused_results = sorted(
        doc_map.values(),
        key=lambda x: x["rrf_score"],
        reverse=True,
    )

    # Replace score with RRF score for consistency
    for result in fused_results:
        result["score"] = result.pop("rrf_score")

    return fused_results