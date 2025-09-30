"""
Grok-4-latest compliance service with RAG
Maintains original interface for zero breaking changes
"""

import os
import json
from typing import Dict, Any

from xai import AsyncXAI
import structlog

from app.models.exceptions import ModelNotAvailableException, ComplianceProcessingException
from app.rag.retriever import hybrid_retrieve

logger = structlog.get_logger()

# Configuration
GROK_MODEL = "grok-4-latest"
TEMPERATURE = float(os.getenv("GROK_TEMP", "0.7"))
TIMEOUT = int(os.getenv("GROK_TIMEOUT", "28"))

# Client singleton
_client: AsyncXAI = None


def _get_client() -> AsyncXAI:
    """Get or create Grok-4 client singleton"""
    global _client

    if _client is None:
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise ModelNotAvailableException(
                message="XAI_API_KEY not set",
                context={"required_env": "XAI_API_KEY"},
            )

        _client = AsyncXAI(api_key=api_key, timeout=TIMEOUT)
        logger.info("grok4.client_initialized", model=GROK_MODEL)

    return _client


async def ask_compliance(query: str, user_id: str = None) -> Dict[str, Any]:
    """
    Send compliance question to Grok-4-latest with RAG context.

    Returns the exact shape the routers expect:
    {"answer": "…", "confidence": "high|medium|low", "risk": "…", "sources": […]}

    Args:
        query: User's compliance question
        user_id: Optional user ID for logging

    Returns:
        Dict with answer, confidence, risk, and sources
    """
    client = _get_client()

    logger.info(
        "grok4.query_started",
        query_length=len(query),
        user_id=user_id,
    )

    try:
        # 1. Retrieve relevant chunks using RAG
        chunks = hybrid_retrieve(query=query, top_k=5)

        logger.debug(
            "grok4.rag_retrieved",
            num_chunks=len(chunks),
        )

        # 2. Build prompt with RAG context
        snippets_text = ""
        sources = []

        for i, chunk in enumerate(chunks, start=1):
            snippets_text += f"[{i}] {chunk['text']}\n"
            snippets_text += f"   Source: {chunk.get('document_title', 'Unknown')} (chunk {chunk.get('chunk_index', 0)})\n\n"

            sources.append({
                "document_id": chunk.get("document_id", "unknown"),
                "document_title": chunk.get("document_title", "Unknown"),
                "chunk_index": chunk.get("chunk_index", 0),
                "relevance_score": chunk.get("score", 0.0),
            })

        system_prompt = (
            "You are an S&P compliance assistant. "
            "Answer ONLY using the provided snippets. "
            "Cite the snippet tag(s) inline (e.g., [1], [2]). "
            "Output valid JSON with this exact structure: "
            '{"answer": "...", "confidence": 0.95, "risk": "low"}'
        )

        user_prompt = f"Snippets:\n{snippets_text}\n\nQuestion: {query}"

        logger.debug(
            "grok4.request",
            model=GROK_MODEL,
            prompt_length=len(user_prompt),
        )

        # 3. Call Grok-4
        response = await client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            timeout=TIMEOUT,
        )

        content = response.choices[0].message.content

        logger.info(
            "grok4.response",
            response_len=len(content),
            finish_reason=response.choices[0].finish_reason,
        )

        # 4. Parse JSON response
        try:
            # Grok-4 returns pure JSON as instructed
            data = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: extract JSON from markdown code blocks
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
                data = json.loads(content)
            else:
                raise

        # 5. Normalize confidence to string
        confidence_score = data.get("confidence", 0.5)
        if confidence_score >= 0.85:
            confidence_level = "high"
        elif confidence_score >= 0.6:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        result = {
            "answer": data.get("answer", "Unable to determine answer from sources."),
            "confidence": confidence_level,
            "confidence_score": confidence_score,
            "risk": data.get("risk", "unknown"),
            "sources": sources,
            "model_used": GROK_MODEL,
        }

        logger.info(
            "grok4.success",
            confidence=confidence_level,
            risk=result["risk"],
            num_sources=len(sources),
        )

        return result

    except ModelNotAvailableException:
        raise

    except json.JSONDecodeError as e:
        logger.error(
            "grok4.json_parse_error",
            error=str(e),
            content_preview=content[:200] if 'content' in locals() else None,
        )
        raise ComplianceProcessingException(
            message="Failed to parse Grok-4 response",
            stage="json_parsing",
            context={"error": str(e)},
        )

    except Exception as e:
        logger.error(
            "grok4.fail",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise ModelNotAvailableException(
            message="Grok-4 unavailable",
            context={"error": str(e)},
        )


async def health_check() -> bool:
    """
    Health check for Grok-4 API.
    Used by /health/detailed endpoint.

    Returns:
        True if Grok-4 is available, False otherwise
    """
    try:
        client = _get_client()

        # Simple ping test
        response = await client.chat.completions.create(
            model=GROK_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            timeout=5,
        )

        return response.choices[0].message.content is not None

    except Exception as e:
        logger.error(
            "grok4.health.fail",
            error=str(e),
        )
        return False