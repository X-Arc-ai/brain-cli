"""Embedding generation for brain nodes (optional -- requires openai package)."""

import os

_client = None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _get_client():
    """Get or create OpenAI client. Lazy-loaded to avoid import cost."""
    global _client
    if _client is None:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI package not installed. "
                "Install with: pip install 'xarc-brain[embeddings]'"
            )
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Set it in your environment or .env file. "
                "Semantic search requires an OpenAI API key."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text string."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMS

    client = _get_client()
    response = client.embeddings.create(
        input=text[:8191],
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single API call."""
    if not texts:
        return []

    client = _get_client()
    cleaned = [t[:8191] if t and t.strip() else " " for t in texts]

    response = client.embeddings.create(
        input=cleaned,
        model=EMBEDDING_MODEL,
    )
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [d.embedding for d in sorted_data]


def node_text_for_embedding(data: dict) -> str:
    """Build the text string to embed for a node."""
    title = data.get("title", "") or ""
    content = data.get("content", "") or ""

    if content:
        return f"{title}. {content}"
    return title
