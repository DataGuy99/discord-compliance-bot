"""
Text splitter for chunking documents into manageable pieces
Uses recursive character splitting with overlap for context preservation
"""

import os
import re
from typing import List

import structlog

logger = structlog.get_logger()


class RecursiveTextSplitter:
    """
    Recursively split text into chunks of specified size with overlap.
    Preserves context by maintaining overlap between chunks.
    """

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        separators: List[str] = None,
    ):
        """
        Initialize text splitter.

        Args:
            chunk_size: Maximum tokens per chunk (default from env)
            chunk_overlap: Token overlap between chunks (default from env)
            separators: List of separators to try, in order
        """
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", "512"))
        self.chunk_overlap = chunk_overlap or int(os.getenv("CHUNK_OVERLAP", "50"))

        # Default separators (try in order)
        self.separators = separators or [
            "\n\n",  # Paragraphs
            "\n",    # Lines
            ". ",    # Sentences
            " ",     # Words
            "",      # Characters
        ]

        logger.info(
            "splitter.initialized",
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks using recursive strategy.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        chunks = []
        current_chunk = ""
        sentences = self._split_by_separators(text, self.separators)

        for sentence in sentences:
            # Estimate token count (rough: 1 token ≈ 4 characters)
            sentence_tokens = len(sentence) // 4

            if len(current_chunk) // 4 + sentence_tokens <= self.chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # Start new chunk with overlap from previous
                overlap_text = self._get_overlap(current_chunk)
                current_chunk = overlap_text + sentence

        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        logger.debug(
            "splitter.split_complete",
            input_length=len(text),
            num_chunks=len(chunks),
        )

        return chunks

    def _split_by_separators(
        self, text: str, separators: List[str]
    ) -> List[str]:
        """
        Split text using the first separator that works.

        Args:
            text: Text to split
            separators: List of separators to try

        Returns:
            List of text pieces
        """
        if not separators:
            return [text]

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator:
            splits = text.split(separator)
        else:
            # Empty separator means split into characters
            splits = list(text)

        # If we got good splits, return them with separator preserved
        if len(splits) > 1:
            result = []
            for i, split in enumerate(splits):
                if split:
                    # Add separator back (except for last split)
                    if i < len(splits) - 1 and separator:
                        result.append(split + separator)
                    else:
                        result.append(split)
            return result

        # If no splits, try next separator
        return self._split_by_separators(text, remaining_separators)

    def _get_overlap(self, text: str) -> str:
        """
        Get overlap text from end of chunk.

        Args:
            text: Text to extract overlap from

        Returns:
            Overlap text
        """
        overlap_chars = self.chunk_overlap * 4  # Token to char estimate
        if len(text) <= overlap_chars:
            return text

        # Get last N characters, but try to break at word boundary
        overlap = text[-overlap_chars:]
        first_space = overlap.find(" ")

        if first_space > 0:
            overlap = overlap[first_space + 1:]

        return overlap

    def split_documents(
        self, documents: List[dict]
    ) -> List[dict]:
        """
        Split multiple documents into chunks.

        Args:
            documents: List of dicts with 'text' and 'metadata' keys

        Returns:
            List of chunk dicts with text and metadata
        """
        all_chunks = []

        for doc in documents:
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})

            chunks = self.split_text(text)

            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    **metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                all_chunks.append({
                    "text": chunk,
                    "metadata": chunk_metadata,
                })

        logger.info(
            "splitter.documents_split",
            num_documents=len(documents),
            total_chunks=len(all_chunks),
        )

        return all_chunks