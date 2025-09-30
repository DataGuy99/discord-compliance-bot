"""
Embedding generation using sentence-transformers
CPU-optimized for Heroku free tier
"""

import os
from typing import List

from sentence_transformers import SentenceTransformer
import structlog

logger = structlog.get_logger()


class Embedder:
    """
    Generate embeddings using sentence-transformers.
    Uses thenlper/gte-small (384-dim, 14MB, CPU-friendly).
    """

    def __init__(self, model_name: str = None):
        """
        Initialize embedder.

        Args:
            model_name: Model to use (default from env)
        """
        self.model_name = model_name or os.getenv("EMBED_MODEL", "thenlper/gte-small")
        self.embed_dim = int(os.getenv("EMBED_DIM", "384"))

        logger.info("embedder.loading", model=self.model_name)

        # Load model (downloads on first run, ~14MB)
        self.model = SentenceTransformer(self.model_name)

        logger.info(
            "embedder.loaded",
            model=self.model_name,
            embed_dim=self.embed_dim,
        )

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (list of floats)
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.embed_dim

        embedding = self.model.encode(text, convert_to_numpy=True)

        return embedding.tolist()

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter out empty texts but keep track of indices
        non_empty_texts = [(i, text) for i, text in enumerate(texts) if text and text.strip()]
        empty_indices = set(range(len(texts))) - {i for i, _ in non_empty_texts}

        if not non_empty_texts:
            # All texts empty
            return [[0.0] * self.embed_dim] * len(texts)

        # Embed non-empty texts
        texts_to_embed = [text for _, text in non_empty_texts]
        embeddings = self.model.encode(
            texts_to_embed,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        # Reconstruct full list with zero vectors for empty texts
        result = []
        non_empty_iter = iter(enumerate(embeddings))
        next_non_empty_idx, next_embedding = next(non_empty_iter, (None, None))

        for i in range(len(texts)):
            if i in empty_indices:
                result.append([0.0] * self.embed_dim)
            else:
                result.append(next_embedding.tolist())
                next_non_empty_idx, next_embedding = next(non_empty_iter, (None, None))

        logger.debug(
            "embedder.batch_complete",
            num_texts=len(texts),
            batch_size=batch_size,
        )

        return result

    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for search query.
        Same as embed_text but kept separate for clarity.

        Args:
            query: Query text

        Returns:
            Query embedding vector
        """
        return self.embed_text(query)