"""
blocker.py — Metaphone-based blocking layer
Responsibility: group entity surfaces into blocks so only same-block pairs are compared.
Reduces O(n²) comparisons to a small multiple via Metaphone phonetic indexing.
"""

from collections import defaultdict
import jellyfish
from loguru import logger


class MetaphoneBlocker:
    """Group entity surfaces by Metaphone phonetic code."""

    # Use Metaphone (via jellyfish) for phonetic blocking.
    # More tolerant than Soundex, works across languages with Latin script.

    def __init__(self, blocking_ratio: float = 0.10):
        """
        blocking_ratio: target ratio of potential pairs to consider.
            If 0.10, we want ~10% of all O(n²) pairs to survive blocking.
            Tighter blocking = faster but riskier; looser = slower but safer.
        """
        self.blocking_ratio = blocking_ratio

    def make_blocks(self, entities: list[str]) -> dict[str, list[str]]:
        """
        Group entities by Metaphone code.
        Returns: {block_key: [entity1, entity2, ...], ...}
        """
        blocks = defaultdict(list)
        for entity in entities:
            code = jellyfish.metaphone(entity)
            blocks[code].append(entity)
        logger.info(f"Blocking: {len(entities)} entities into {len(blocks)} blocks")
        return dict(blocks)

    def get_candidate_pairs(
        self, entities: list[str]
    ) -> list[tuple[str, str]]:
        """
        Return all candidate (a, b) pairs within each block.
        Avoids self-pairs (a, a) and duplicates (a, b) == (b, a).
        """
        blocks = self.make_blocks(entities)
        pairs = []

        for block_members in blocks.values():
            # Within-block pairwise comparisons
            for i, a in enumerate(block_members):
                for b in block_members[i + 1 :]:
                    pairs.append((a, b))

        logger.info(
            f"Blocking produced {len(pairs)} candidate pairs "
            f"(ratio: {len(pairs) / (len(entities) ** 2 / 2):.4f})"
        )
        return pairs
