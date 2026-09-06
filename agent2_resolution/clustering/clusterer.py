"""
clusterer.py — Hierarchical Agglomerative Clustering (HAC) for entity resolution
Responsibility: take pairwise similarities, build a dendrogram, cut at thresholds,
and produce entity clusters + pending_review decisions.
"""

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform
from loguru import logger

from agent2_resolution.config import settings
from agent2_resolution.models.schemas import (
    EntityCluster,
    EntityMention,
    ResolutionDecision,
    ResolutionPair,
)


class EntityClusterer:
    """Hierarchical clustering engine for resolved entities."""

    def __init__(self, linkage_method: str = settings.HAC_LINKAGE):
        self.linkage_method = linkage_method

    def cluster(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
    ) -> tuple[list[EntityCluster], list[ResolutionPair]]:
        """
        Cluster mentions via HAC. Split into three bins: merged, pending_review, rejected.

        Args:
            mentions: list of EntityMention objects
            embeddings: (N, D) float32 embedding matrix, unit-normed

        Returns:
            (clusters, pending_review_pairs)
        """
        if len(mentions) <= 1:
            # No clustering to do
            if mentions:
                clu = EntityCluster(
                    cluster_id="CLU-00001",
                    canonical=mentions[0].surface,
                    entity_type=mentions[0].entity_type,
                    members=[mentions[0]],
                    avg_similarity=1.0,
                )
                return [clu], []
            return [], []

        # Compute pairwise cosine distances (1 - similarity)
        # For unit-norm vectors: cosine(a, b) = a · b
        similarities = embeddings @ embeddings.T
        distances = 1.0 - similarities
        np.fill_diagonal(distances, 0)  # Self-distance = 0

        # Upper triangle only (condensed distance matrix)
        dist_condensed = squareform(distances, checks=False)

        # Build linkage matrix via HAC
        try:
            Z = linkage(dist_condensed, method=self.linkage_method)
        except Exception as e:
            logger.error(f"Linkage failed: {e}")
            return [], []

        # Cut the dendrogram at different thresholds to get cluster assignments
        # distance threshold = 1 - similarity threshold
        # For merged (sim >= 0.95): dist <= 0.05
        # For pending (sim in [0.80, 0.95)): dist in (0.05, 0.20]

        clusters_merged = self._cut_and_build(
            Z, mentions, embeddings, dist_threshold=0.05, min_similarity=0.95
        )

        pending_review_pairs = self._extract_pending_pairs(
            mentions, embeddings, min_sim=0.80, max_sim=0.95
        )

        logger.info(
            f"HAC produced {len(clusters_merged)} clusters, "
            f"{len(pending_review_pairs)} pending pairs"
        )

        return clusters_merged, pending_review_pairs

    # ── Internal helpers ─────────────────────────────────────────────────────────

    def _cut_and_build(
        self,
        Z: np.ndarray,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        dist_threshold: float,
        min_similarity: float,
    ) -> list[EntityCluster]:
        """Cut the dendrogram at dist_threshold and build EntityCluster objects with centroid embeddings."""
        cluster_labels = fcluster(Z, dist_threshold, criterion="distance")

        clusters_dict = {}
        for label, mention, emb in zip(cluster_labels, mentions, embeddings):
            if label not in clusters_dict:
                clusters_dict[label] = []
            clusters_dict[label].append((mention, emb))

        result = []
        for cluster_id, (label, members_with_emb) in enumerate(
            clusters_dict.items(), start=1
        ):
            member_mentions = [m for m, _ in members_with_emb]
            member_embeds = np.array([e for _, e in members_with_emb])

            # Elect canonical (longest name, or first if all equal)
            canonical = max(member_mentions, key=lambda m: len(m.surface)).surface

            # Compute intra-cluster average similarity
            if len(member_embeds) > 1:
                sims = member_embeds @ member_embeds.T
                np.fill_diagonal(sims, 0)
                avg_sim = np.mean(sims[np.triu_indices_from(sims, k=1)])
            else:
                avg_sim = 1.0

            # Calculate centroid embedding (mean of member embeddings, normalized)
            centroid = np.mean(member_embeds, axis=0)
            centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-9)
            centroid_list = centroid_norm.astype(np.float32).tolist()

            entity_type = member_mentions[0].entity_type

            clu = EntityCluster(
                cluster_id=f"CLU-{cluster_id:05d}",
                canonical=canonical,
                entity_type=entity_type,
                members=member_mentions,
                avg_similarity=avg_sim,
                centroid_embedding=centroid_list,
            )
            result.append(clu)

        return result

    def _extract_pending_pairs(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        min_sim: float = 0.80,
        max_sim: float = 0.95,
    ) -> list[ResolutionPair]:
        """Extract all (a, b) pairs falling in the pending_review band."""
        pairs = []
        sims = embeddings @ embeddings.T

        for i, mention_a in enumerate(mentions):
            for j, mention_b in enumerate(mentions[i + 1 :], start=i + 1):
                sim = float(sims[i, j])
                if min_sim <= sim < max_sim:
                    pair = ResolutionPair(
                        mention_a=mention_a.surface,
                        mention_b=mention_b.surface,
                        similarity=sim,
                        decision=ResolutionDecision.PENDING_REVIEW,
                    )
                    pairs.append(pair)

        return pairs
