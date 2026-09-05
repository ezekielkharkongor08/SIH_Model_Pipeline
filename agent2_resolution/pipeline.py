"""
pipeline.py — Master orchestrator for Agent 2: Entity Resolution
Responsibility: take raw extracted entity mentions from Agent 1 batches,
embed them with BGE-m3, block with Metaphone, cluster with HAC,
apply the 0.95/0.80 threshold matrix, and return structured clusters + pending_review.
Now also builds connected graph: tracks entity IDs, resolved triples, and evidence sources.
"""

import time
import uuid
from collections import defaultdict
from typing import Dict, Optional, Set
from loguru import logger

from agent2_resolution.embeddings.embedder import BGEEmbedder
from agent2_resolution.blocking.blocker import MetaphoneBlocker
from agent2_resolution.clustering.clusterer import EntityClusterer
from agent2_resolution.storage.database import ResolutionRepository
from agent2_resolution.models.schemas import (
    EntityMention,
    ResolutionPayload,
    ResolvedTriple,
    ClusterEvidenceSource,
)
from agent1_extraction.models.schemas import ExtractionPayload, ExtractedTriple
from agent1_extraction.config import settings as agent1_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class EntityResolutionPipeline:
    """
    Master Orchestrator for Agent 2: Entity Resolution.

    Input:  List of Agent 1 ExtractionPayload objects (or raw mentions)
    Output: ResolutionPayload with resolved clusters + pending_review + graph data
    """

    def __init__(self):
        self.embedder = BGEEmbedder()
        self.blocker = MetaphoneBlocker()
        self.clusterer = EntityClusterer()
        self.db_repo = ResolutionRepository()

        # Separate session to look up entity IDs from Agent1 tables
        self.agent1_engine = create_engine(agent1_settings.DATABASE_URL, pool_pre_ping=True)
        self.agent1_session = sessionmaker(bind=self.agent1_engine)

    def _lookup_entity_id(
        self, session, canonical_name: str, evidence_id: str
    ) -> Optional[int]:
        """Look up the entity ID from extracted_entities table."""
        from sqlalchemy import text
        try:
            result = session.execute(
                text("""
                    SELECT id FROM extracted_entities
                    WHERE canonical_name = :name AND evidence_id = :evid
                    LIMIT 1
                """),
                {"name": canonical_name, "evid": evidence_id}
            )
            row = result.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f"Failed to lookup entity ID for '{canonical_name}': {e}")
            return None

    def _lookup_triple_ids(
        self, session, subject_name: str, predicate: str, object_name: str, evidence_id: str
    ) -> Optional[int]:
        """Look up the triple ID from extracted_triples table."""
        from sqlalchemy import text
        try:
            result = session.execute(
                text("""
                    SELECT id FROM extracted_triples
                    WHERE subject_name = :subj
                    AND predicate = :pred
                    AND object_name = :obj
                    AND evidence_id = :evid
                    LIMIT 1
                """),
                {"subj": subject_name, "pred": predicate, "obj": object_name, "evid": evidence_id}
            )
            row = result.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f"Failed to lookup triple ID: {e}")
            return None

    def _build_cluster_map(
        self, clusters: list, mentions: list[EntityMention]
    ) -> Dict[str, str]:
        """Map (surface, evidence_id) -> cluster_id for triple matching."""
        cluster_map = {}
        for cluster in clusters:
            for member in cluster.members:
                key = (member.surface.lower(), member.evidence_id)
                cluster_map[key] = cluster.cluster_id
        return cluster_map

    # ── Main Entry Point: from Agent 1 ExtractionPayloads ──────────────────────

    def process(
        self, payloads: list[ExtractionPayload]
    ) -> ResolutionPayload:
        """
        Process a batch of Agent 1 ExtractionPayload objects.
        Extracts all entity mentions, groups them by entity_type,
        and runs resolution independently per type with globally unique cluster IDs.

        Also builds relational graph data: entity IDs, resolved triples, evidence sources.
        """
        start_time = time.time()
        run_id = f"RES-{uuid.uuid4().hex[:8].upper()}"

        # 1. Collect all mentions across all payloads, with entity IDs
        all_mentions: list[EntityMention] = []
        all_triples: list[ExtractedTriple] = []
        evidence_ids: set[str] = set()

        agent1_session = self.agent1_session()
        try:
            for p in payloads:
                evidence_ids.add(p.evidence_id)
                for e in p.entities:
                    # Look up entity ID for graph linking
                    entity_id = self._lookup_entity_id(
                        agent1_session, e.canonical_name, p.evidence_id
                    )
                    all_mentions.append(
                        EntityMention(
                            surface=e.canonical_name,
                            entity_type=e.entity_type.value
                            if hasattr(e.entity_type, "value")
                            else str(e.entity_type),
                            evidence_id=p.evidence_id,
                            confidence=e.confidence,
                            entity_id=entity_id,
                        )
                    )
                # Collect triples for graph edge building
                all_triples.extend(p.triples)
        finally:
            agent1_session.close()

        logger.info(
            f"Agent 2 received {len(all_mentions)} mentions "
            f"and {len(all_triples)} triples "
            f"across {len(evidence_ids)} evidence batches"
        )

        if not all_mentions:
            return ResolutionPayload(
                run_id=run_id,
                evidence_ids=list(evidence_ids),
                clusters=[],
                pending_review=[],
                resolved_triples=[],
                evidence_sources=[],
                total_mentions=0,
                total_clusters=0,
                total_triples=0,
                execution_time_ms=0.0,
                status="SUCCESS",
            )

        # 2. Group by entity_type — only resolve within same type
        by_type: dict[str, list[EntityMention]] = defaultdict(list)
        for m in all_mentions:
            by_type[m.entity_type].append(m)

        all_clusters = []
        all_pending = []

        # Global counter ensures unique cluster_ids across all entity types per run
        global_cluster_counter = 1

        # 3. Resolve each entity_type independently
        for entity_type, mentions in by_type.items():
            logger.info(
                f"Resolving type='{entity_type}' ({len(mentions)} mentions)"
            )

            # Deduplicate by surface text within the batch to keep HAC fast
            unique_surfaces = list({m.surface: m for m in mentions}.values())
            surfaces = [m.surface for m in unique_surfaces]

            # Embed using BGE-m3
            embeddings = self.embedder.embed_batch(surfaces)

            # Block candidate pairs via Metaphone
            candidate_pairs = self.blocker.get_candidate_pairs(surfaces)

            # Cluster via HAC and threshold matrix
            clusters, pending = self.clusterer.cluster(
                unique_surfaces, embeddings
            )

            # Re-assign globally unique cluster_ids across all entity types
            for c in clusters:
                c.cluster_id = f"CLU-{global_cluster_counter:05d}"
                global_cluster_counter += 1

            all_clusters.extend(clusters)
            all_pending.extend(pending)

        # 4. Build cluster mapping for triple resolution
        cluster_map = self._build_cluster_map(all_clusters, all_mentions)

        # 5. Build resolved triples (graph edges) from Agent1 triples
        resolved_triples: list[ResolvedTriple] = []
        agent1_session = self.agent1_session()
        try:
            for triple in all_triples:
                subj_key = (triple.subject.canonical_name.lower(), triple.evidence_id)
                obj_key = (triple.object.canonical_name.lower(), triple.evidence_id)

                subj_cluster = cluster_map.get(subj_key)
                obj_cluster = cluster_map.get(obj_key)

                if subj_cluster and obj_cluster:
                    # Lookup original triple ID
                    original_id = self._lookup_triple_ids(
                        agent1_session,
                        triple.subject.canonical_name,
                        triple.predicate,
                        triple.object.canonical_name,
                        triple.evidence_id
                    )

                    resolved_triples.append(
                        ResolvedTriple(
                            subject_cluster_id=subj_cluster,
                            predicate=triple.predicate,
                            object_cluster_id=obj_cluster,
                            original_triple_id=original_id,
                            confidence=triple.confidence,
                            raw_timestamp=triple.raw_timestamp,
                            raw_geo=triple.raw_geo,
                            latitude=triple.normalized_geo.latitude if triple.normalized_geo else None,
                            longitude=triple.normalized_geo.longitude if triple.normalized_geo else None,
                        )
                    )
        finally:
            agent1_session.close()

        # 6. Build evidence sources per cluster
        evidence_sources: list[ClusterEvidenceSource] = []
        cluster_evidence_count: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for cluster in all_clusters:
            for member in cluster.members:
                cluster_evidence_count[cluster.cluster_id][member.evidence_id] += 1

        for cluster_id, evid_counts in cluster_evidence_count.items():
            for evid_id, count in evid_counts.items():
                evidence_sources.append(
                    ClusterEvidenceSource(
                        cluster_id=cluster_id,
                        evidence_id=evid_id,
                        mention_count=count,
                    )
                )

        execution_time = round((time.time() - start_time) * 1000, 2)

        # 7. Build final payload with all graph data
        res_payload = ResolutionPayload(
            run_id=run_id,
            evidence_ids=list(evidence_ids),
            clusters=all_clusters,
            pending_review=all_pending,
            resolved_triples=resolved_triples,
            evidence_sources=evidence_sources,
            total_mentions=len(all_mentions),
            total_clusters=len(all_clusters),
            total_triples=len(resolved_triples),
            execution_time_ms=execution_time,
            status="SUCCESS",
        )

        # 8. Persist to DB
        try:
            self.db_repo.save_resolution(res_payload)
        except Exception as e:
            logger.error(f"Failed to persist resolution payload: {e}")

        return res_payload

    # ── Convenience Entry Point: Direct mention objects ────────────────────────

    def resolve_mentions(
        self, mentions: list[EntityMention]
    ) -> ResolutionPayload:
        """Direct resolution from a list of mentions without full payloads."""
        start_time = time.time()
        run_id = f"RES-{uuid.uuid4().hex[:8].upper()}"

        if not mentions:
            return ResolutionPayload(
                run_id=run_id,
                evidence_ids=[],
                clusters=[],
                pending_review=[],
                resolved_triples=[],
                evidence_sources=[],
                total_mentions=0,
                total_clusters=0,
                total_triples=0,
                execution_time_ms=0.0,
                status="SUCCESS",
            )

        surfaces = [m.surface for m in mentions]
        embeddings = self.embedder.embed_batch(surfaces)
        clusters, pending = self.clusterer.cluster(mentions, embeddings)

        execution_time = round((time.time() - start_time) * 1000, 2)

        # Build evidence sources
        evidence_sources: list[ClusterEvidenceSource] = []
        cluster_evidence_count: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for cluster in clusters:
            for member in cluster.members:
                cluster_evidence_count[cluster.cluster_id][member.evidence_id] += 1

        for cluster_id, evid_counts in cluster_evidence_count.items():
            for evid_id, count in evid_counts.items():
                evidence_sources.append(
                    ClusterEvidenceSource(
                        cluster_id=cluster_id,
                        evidence_id=evid_id,
                        mention_count=count,
                    )
                )

        return ResolutionPayload(
            run_id=run_id,
            evidence_ids=list({m.evidence_id for m in mentions}),
            clusters=clusters,
            pending_review=pending,
            resolved_triples=[],
            evidence_sources=evidence_sources,
            total_mentions=len(mentions),
            total_clusters=len(clusters),
            total_triples=0,
            execution_time_ms=execution_time,
            status="SUCCESS",
        )