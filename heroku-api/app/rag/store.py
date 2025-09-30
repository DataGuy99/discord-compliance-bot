"""
Redis vector store for RAG chunks
Uses RediSearch for vector similarity search
"""

import os
from typing import List, Dict, Any
import hashlib
import json

import redis
from redis.commands.search.field import TextField, VectorField, NumericField, TagField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
import structlog

logger = structlog.get_logger()


class VectorStore:
    """
    Redis-based vector store for document chunks.
    Supports vector similarity search and metadata filtering.
    """

    def __init__(self, redis_url: str = None, index_name: str = "compliance_docs"):
        """
        Initialize vector store.

        Args:
            redis_url: Redis connection URL (default from env)
            index_name: Name of the search index
        """
        self.redis_url = redis_url or os.getenv("REDIS_VECTOR_URL", "redis://localhost:6379/0")
        self.index_name = index_name
        self.embed_dim = int(os.getenv("EMBED_DIM", "384"))

        # Connect to Redis
        self.client = redis.from_url(
            self.redis_url,
            decode_responses=False,  # Keep binary for vectors
            socket_timeout=5,
            socket_connect_timeout=5,
        )

        # Initialize index
        self._create_index()

        logger.info(
            "vectorstore.initialized",
            index_name=self.index_name,
            embed_dim=self.embed_dim,
        )

    def _create_index(self):
        """Create RediSearch index if it doesn't exist"""
        try:
            # Check if index exists
            self.client.ft(self.index_name).info()
            logger.debug("vectorstore.index_exists", index_name=self.index_name)
            return
        except redis.ResponseError:
            # Index doesn't exist, create it
            pass

        schema = (
            TextField("chunk_text", weight=1.0),
            VectorField(
                "embedding",
                "FLAT",
                {
                    "TYPE": "FLOAT32",
                    "DIM": self.embed_dim,
                    "DISTANCE_METRIC": "COSINE",
                },
            ),
            TextField("document_id"),
            TextField("document_title"),
            TextField("source"),
            NumericField("chunk_index"),
            TagField("document_type"),
            TagField("category"),
        )

        definition = IndexDefinition(
            prefix=[f"{self.index_name}:"],
            index_type=IndexType.HASH,
        )

        self.client.ft(self.index_name).create_index(
            fields=schema,
            definition=definition,
        )

        logger.info("vectorstore.index_created", index_name=self.index_name)

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Add chunks to vector store.

        Args:
            chunks: List of chunk dicts with 'text', 'embedding', 'metadata'

        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0

        pipeline = self.client.pipeline(transaction=False)

        for chunk in chunks:
            chunk_id = self._generate_chunk_id(chunk)
            key = f"{self.index_name}:{chunk_id}"

            # Prepare data for Redis
            metadata = chunk.get("metadata", {})
            embedding_bytes = self._embedding_to_bytes(chunk["embedding"])

            data = {
                "chunk_text": chunk["text"],
                "embedding": embedding_bytes,
                "document_id": metadata.get("document_id", "unknown"),
                "document_title": metadata.get("document_title", ""),
                "source": metadata.get("source", ""),
                "chunk_index": metadata.get("chunk_index", 0),
                "document_type": metadata.get("document_type", "unknown"),
                "category": metadata.get("category", "general"),
            }

            pipeline.hset(key, mapping=data)

        pipeline.execute()

        logger.info(
            "vectorstore.chunks_added",
            num_chunks=len(chunks),
            index_name=self.index_name,
        )

        return len(chunks)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of matching chunks with scores
        """
        # Convert embedding to bytes
        query_vector = self._embedding_to_bytes(query_embedding)

        # Build query
        base_query = f"*=>[KNN {top_k} @embedding $vec AS score]"

        # Add filters if provided
        if filters:
            filter_parts = []
            for key, value in filters.items():
                if key == "document_type" or key == "category":
                    filter_parts.append(f"@{key}:{{{value}}}")
                elif key == "document_id":
                    filter_parts.append(f"@{key}:{value}")

            if filter_parts:
                base_query = "(" + " ".join(filter_parts) + f")=>[KNN {top_k} @embedding $vec AS score]"

        query = (
            Query(base_query)
            .sort_by("score")
            .return_fields("chunk_text", "document_id", "document_title", "source", "chunk_index", "score")
            .dialect(2)
        )

        try:
            results = self.client.ft(self.index_name).search(
                query,
                query_params={"vec": query_vector},
            )
        except redis.ResponseError as e:
            logger.error("vectorstore.search_error", error=str(e))
            return []

        chunks = []
        for doc in results.docs:
            chunks.append({
                "text": doc.chunk_text,
                "document_id": doc.document_id,
                "document_title": doc.document_title,
                "source": doc.source,
                "chunk_index": int(doc.chunk_index),
                "score": float(doc.score),
            })

        logger.debug(
            "vectorstore.search_complete",
            num_results=len(chunks),
            top_k=top_k,
        )

        return chunks

    def delete_by_document(self, document_id: str) -> int:
        """
        Delete all chunks for a document.

        Args:
            document_id: Document ID to delete

        Returns:
            Number of chunks deleted
        """
        query = Query(f"@document_id:{document_id}").return_fields("id")

        try:
            results = self.client.ft(self.index_name).search(query)
        except redis.ResponseError:
            return 0

        if not results.docs:
            return 0

        pipeline = self.client.pipeline(transaction=False)
        for doc in results.docs:
            pipeline.delete(doc.id)

        pipeline.execute()

        logger.info(
            "vectorstore.document_deleted",
            document_id=document_id,
            num_chunks=len(results.docs),
        )

        return len(results.docs)

    def count_chunks(self) -> int:
        """
        Count total chunks in store.

        Returns:
            Total number of chunks
        """
        try:
            info = self.client.ft(self.index_name).info()
            return int(info["num_docs"])
        except redis.ResponseError:
            return 0

    def _generate_chunk_id(self, chunk: Dict[str, Any]) -> str:
        """Generate unique ID for chunk based on content"""
        metadata = chunk.get("metadata", {})
        content = f"{metadata.get('document_id', '')}:{metadata.get('chunk_index', 0)}:{chunk['text'][:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _embedding_to_bytes(self, embedding: List[float]) -> bytes:
        """Convert embedding list to bytes for Redis"""
        import struct
        return struct.pack(f"{len(embedding)}f", *embedding)

    def _bytes_to_embedding(self, data: bytes) -> List[float]:
        """Convert bytes back to embedding list"""
        import struct
        num_floats = len(data) // 4
        return list(struct.unpack(f"{num_floats}f", data))

    def close(self):
        """Close Redis connection"""
        self.client.close()
        logger.info("vectorstore.closed")