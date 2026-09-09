"""
clusterer.py — Hierarchical Agglomerative Clustering (HAC) for entity resolution
Responsibility: take pairwise similarities, build a dendrogram, cut at thresholds,
and produce entity clusters + pending_review decisions with strict entity-type blocking.
"""

from typing import Any
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from loguru import logger

from agent2_resolution.config import settings
from agent2_resolution.models.schemas import (
    EntityCluster,
    EntityMention,
    ResolutionDecision,
    ResolutionPair,
)

# Expanded set of entity types that represent discrete, scalar, or precise identifier values
EXACT_MATCH_TYPES = {
    # Core Scalar & Procedural Identifiers
    "PHONE_NUMBER",
    "MONEY_AMOUNT",
    "DATE_TIME",
    "TRANSACTION_ID",
    "LEGAL_SECTION",
    "IDENTIFIER",            # Aadhaar, PAN, SSN, Tax IDs, etc.
    "FIR_NUMBER",
    "CASE_NUMBER",           # Court / Police case numbers
    
    # Financial & Payment Identifiers
    "FINANCIAL_INSTRUMENT",  # Cheque numbers, credit/debit card numbers
    "CRYPTO_WALLET",         # BTC/ETH wallet addresses
    "UPI_ID",                # UPI / VPA payment handles
    
    # Digital & Cyber Artifacts
    "DIGITAL_ARTIFACT",      # IP addresses, MAC addresses, Hashes (MD5/SHA), URLs, Domains
    "SOCIAL_MEDIA_HANDLE",   # Usernames, social media account handles
    
    # Documents & Official Evidence
    "DOCUMENT",              # Passports, Warrant IDs, National ID card numbers
    "PHYSICAL_EVIDENCE",     # DNA profile IDs, Fingerprint records, Evidence tag numbers
    "MEASUREMENT",           # Exact quantities, weights, speeds
    "DEVICE",                # Hardware/Device serial numbers
    "SOFTWARE",              # Software names, versions, malware signatures
}


def is_exact_match_type(entity_type: Any) -> bool:
    """Helper function to normalize and verify if an entity type requires exact string matching."""
    if hasattr(entity_type, "value"):
        val = str(entity_type.name if hasattr(entity_type, "name") else entity_type.value)
    else:
        val = str(entity_type)
    
    val_clean = val.strip().upper().replace(" ", "_").replace("-", "_")
    return val_clean in EXACT_MATCH_TYPES


class EntityClusterer:
    """Hierarchical clustering engine for resolved entities."""

    def __init__(self, linkage_method: str = getattr(settings, "HAC_LINKAGE", "average")):
        self.linkage_method = linkage_method

        # Threshold Settings
        # Auto-merge threshold (similarity >= AUTO_MERGE_SIMILARITY)
        self.auto_merge_similarity = getattr(settings, "AUTO_MERGE_SIMILARITY", 0.96)
        
        # Pending review band (PENDING_MIN_SIMILARITY <= similarity < AUTO_MERGE_SIMILARITY)
        self.pending_min_similarity = getattr(settings, "PENDING_MIN_SIMILARITY", 0.88)

    def cluster(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
    ) -> tuple[list[EntityCluster], list[ResolutionPair]]:
        """
        Cluster mentions via HAC with domain isolation (entity-type blocking).

        Args:
            mentions: list of EntityMention objects
            embeddings: (N, D) float32 embedding matrix, unit-normed

        Returns:
            tuple[list[EntityCluster], list[ResolutionPair]]
        """
        if not mentions:
            return [], []

        if len(mentions) == 1:
            m = mentions[0]
            clu = EntityCluster(
                cluster_id="CLU-00001",
                canonical=m.surface,
                entity_type=m.entity_type,
                members=[m],
                avg_similarity=1.0,
                centroid_embedding=embeddings[0].astype(np.float32).tolist(),
            )
            return [clu], []

        # Step 1: Partition mentions and embeddings by entity_type (Blocking / Domain Isolation)
        type_groups: dict[str, list[tuple[EntityMention, np.ndarray]]] = {}
        for mention, emb in zip(mentions, embeddings):
            e_type_key = str(mention.entity_type.value) if hasattr(mention.entity_type, "value") else str(mention.entity_type)
            if e_type_key not in type_groups:
                type_groups[e_type_key] = []
            type_groups[e_type_key].append((mention, emb))

        all_clusters: list[EntityCluster] = []
        all_pending_pairs: list[ResolutionPair] = []
        cluster_counter = 1

        # Step 2: Cluster each partition independently
        for entity_type_key, items in type_groups.items():
            sub_mentions = [item[0] for item in items]
            sub_embeddings = np.array([item[1] for item in items])

            # Route A: Exact matching for scalar/discrete entity types
            if is_exact_match_type(entity_type_key):
                clusters, pending_pairs = self._cluster_exact(
                    sub_mentions, sub_embeddings, start_id=cluster_counter
                )
            # Route B: Vector HAC for natural language entity types (PERSON, ORGANIZATION, LOCATION, UNKNOWN, etc.)
            else:
                clusters, pending_pairs = self._cluster_hac(
                    sub_mentions, sub_embeddings, start_id=cluster_counter
                )

            all_clusters.extend(clusters)
            all_pending_pairs.extend(pending_pairs)
            cluster_counter += len(clusters)

        logger.info(
            f"Clustering complete: {len(all_clusters)} clusters created, "
            f"{len(all_pending_pairs)} pending pairs queued across {len(type_groups)} entity types."
        )

        return all_clusters, all_pending_pairs

    # ── Internal Clustering Helpers ──────────────────────────────────────────────

    def _cluster_exact(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        start_id: int,
    ) -> tuple[list[EntityCluster], list[ResolutionPair]]:
        """Group discrete scalar entity types strictly by exact normalized surface string."""
        groups: dict[str, list[tuple[EntityMention, np.ndarray]]] = {}

        for mention, emb in zip(mentions, embeddings):
            norm_key = mention.surface.strip().lower()
            if norm_key not in groups:
                groups[norm_key] = []
            groups[norm_key].append((mention, emb))

        clusters = []
        for i, (key, group_items) in enumerate(groups.items(), start=start_id):
            member_mentions = [m for m, _ in group_items]
            member_embeds = np.array([e for _, e in group_items])

            centroid = np.mean(member_embeds, axis=0)
            centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-9)

            clu = EntityCluster(
                cluster_id=f"CLU-{i:05d}",
                canonical=member_mentions[0].surface,
                entity_type=member_mentions[0].entity_type,
                members=member_mentions,
                avg_similarity=1.0,
                centroid_embedding=centroid_norm.astype(np.float32).tolist(),
            )
            clusters.append(clu)

        # Discrete types generate zero false-positive review candidate pairs
        return clusters, []

    def _cluster_hac(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        start_id: int,
    ) -> tuple[list[EntityCluster], list[ResolutionPair]]:
        """Perform Hierarchical Agglomerative Clustering for natural language entities."""
        if len(mentions) == 1:
            m = mentions[0]
            clu = EntityCluster(
                cluster_id=f"CLU-{start_id:05d}",
                canonical=m.surface,
                entity_type=m.entity_type,
                members=[m],
                avg_similarity=1.0,
                centroid_embedding=embeddings[0].astype(np.float32).tolist(),
            )
            return [clu], []

        # Compute cosine distance matrix (1 - cosine_similarity)
        similarities = embeddings @ embeddings.T
        distances = np.clip(1.0 - similarities, 0.0, None)
        np.fill_diagonal(distances, 0.0)

        dist_condensed = squareform(distances, checks=False)

        try:
            Z = linkage(dist_condensed, method=self.linkage_method)
        except Exception as e:
            logger.error(f"HAC linkage failed for entity type '{mentions[0].entity_type}': {e}")
            clusters = []
            for idx, (m, emb) in enumerate(zip(mentions, embeddings), start=start_id):
                clusters.append(
                    EntityCluster(
                        cluster_id=f"CLU-{idx:05d}",
                        canonical=m.surface,
                        entity_type=m.entity_type,
                        members=[m],
                        avg_similarity=1.0,
                        centroid_embedding=emb.astype(np.float32).tolist(),
                    )
                )
            return clusters, []

        # Distance threshold = 1.0 - auto_merge_similarity
        dist_threshold = 1.0 - self.auto_merge_similarity

        clusters_merged = self._cut_and_build(
            Z,
            mentions,
            embeddings,
            dist_threshold=dist_threshold,
            start_id=start_id,
        )

        pending_review_pairs = self._extract_pending_pairs(
            mentions,
            embeddings,
            min_sim=self.pending_min_similarity,
            max_sim=self.auto_merge_similarity,
        )

        return clusters_merged, pending_review_pairs

    def _cut_and_build(
        self,
        Z: np.ndarray,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        dist_threshold: float,
        start_id: int,
    ) -> list[EntityCluster]:
        """Cut the dendrogram at dist_threshold and construct EntityCluster objects."""
        cluster_labels = fcluster(Z, dist_threshold, criterion="distance")

        clusters_dict: dict[int, list[tuple[EntityMention, np.ndarray]]] = {}
        for label, mention, emb in zip(cluster_labels, mentions, embeddings):
            if label not in clusters_dict:
                clusters_dict[label] = []
            clusters_dict[label].append((mention, emb))

        result = []
        for offset, (label, members_with_emb) in enumerate(clusters_dict.items()):
            current_id = start_id + offset
            member_mentions = [m for m, _ in members_with_emb]
            member_embeds = np.array([e for _, e in members_with_emb])

            # Elect canonical name (longest surface string)
            canonical = max(member_mentions, key=lambda m: len(m.surface)).surface

            # Compute intra-cluster average similarity
            if len(member_embeds) > 1:
                sims = member_embeds @ member_embeds.T
                np.fill_diagonal(sims, 0.0)
                avg_sim = float(np.mean(sims[np.triu_indices_from(sims, k=1)]))
            else:
                avg_sim = 1.0

            # Compute centroid embedding
            centroid = np.mean(member_embeds, axis=0)
            centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-9)

            clu = EntityCluster(
                cluster_id=f"CLU-{current_id:05d}",
                canonical=canonical,
                entity_type=member_mentions[0].entity_type,
                members=member_mentions,
                avg_similarity=avg_sim,
                centroid_embedding=centroid_norm.astype(np.float32).tolist(),
            )
            result.append(clu)

        return result

    def _extract_pending_pairs(
        self,
        mentions: list[EntityMention],
        embeddings: np.ndarray,
        min_sim: float,
        max_sim: float,
    ) -> list[ResolutionPair]:
        """Extract candidate pairs falling strictly within the pending_review band."""
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