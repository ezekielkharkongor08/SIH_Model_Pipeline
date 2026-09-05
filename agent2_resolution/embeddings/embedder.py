"""
embedder.py — BGE-m3 embedding layer
Responsibility: convert an entity surface string → a unit-norm float32 vector.
Keeps the model loaded once (singleton-style) so repeated calls are fast.
"""

import numpy as np
from loguru import logger

from agent2_resolution.config import settings


class BGEEmbedder:
    """Wraps sentence-transformers' BGE-m3 for entity surface embedding."""

    def __init__(self):
        # Lazy-load: the heavy import lives here so tests can monkey-patch easily
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                settings.EMBED_MODEL,
                device=settings.EMBED_DEVICE,
            )
            logger.info(f"BGE-m3 loaded on device='{settings.EMBED_DEVICE}'")
        except Exception as e:
            # For demo/CI environments where the model is unavailable,
            # fall back to a deterministic hash-based dummy embedding.
            logger.warning(
                f"sentence-transformers unavailable ({e}). "
                "Using deterministic stub embeddings — not for production."
            )
            self._model = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def embed(self, text: str) -> np.ndarray:
        """Return a unit-norm vector for a single entity surface string."""
        if self._model is not None:
            vec = self._model.encode(text, normalize_embeddings=True)
            return np.array(vec, dtype=np.float32)
        return self._stub_embed(text)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Return an (N, D) float32 matrix, one row per text, unit-normed."""
        if not texts:
            return np.empty((0,), dtype=np.float32)
        if self._model is not None:
            vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=64)
            return np.array(vecs, dtype=np.float32)
        return np.stack([self._stub_embed(t) for t in texts])

    # ── Stub (demo/CI only) ────────────────────────────────────────────────────

    @staticmethod
    def _stub_embed(text: str, dim: int = 128) -> np.ndarray:
        """Deterministic, reproducible dummy embedding derived from text hash."""
        seed = int.from_bytes(text.lower().encode()[:8].ljust(8, b"\x00"), "big")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(dim).astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)
