"""
database.py — Storage layer for Agent 2 resolution results
Responsibility: persist clusters and pending_review decisions to the shared Postgres DB.
Uses same connection as Agent 1, adds entity_clusters and resolution_decisions tables.
Includes full relational graph support: memberships, resolved triples, evidence sources.
"""

import json

from agent2_resolution.config import settings
from agent2_resolution.models.schemas import (
    EntityCluster,
    ResolutionPayload,
    ResolutionPair,
    ResolvedTriple,
    ClusterEvidenceSource,
)
from loguru import logger
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import relationship, sessionmaker

from agent1_extraction.storage.database import (
    Base,
    EntityModel,
    EvidenceModel,
    TripleModel,
)


class ClusterModel(Base):
    """Resolved entity cluster (one row = one final entity node)."""
    __tablename__ = "entity_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(128), nullable=False, index=True)
    cluster_id = Column(String(64), nullable=False, unique=True)
    canonical_name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)
    avg_similarity = Column(Float, nullable=False)
    member_count = Column(Integer, nullable=False)
    # pgvector column for centroid embedding (BGE-m3 = 1024 dimensions)
    centroid_embedding = Column(Text, nullable=True)  # Stored as JSON string, parsed on read
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships for graph traversal
    memberships = relationship("ClusterMembershipModel", back_populates="cluster", cascade="all, delete-orphan")
    evidence_sources = relationship("ClusterEvidenceSourceModel", back_populates="cluster", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_clusters_centroid_hnsw", "centroid_embedding", postgresql_using="gin",
              postgresql_ops={"centroid_embedding": "vector_cosine_ops"}),
    )


class ResolutionPairModel(Base):
    """Pending review decision (one row = one candidate pair in the 0.80–0.94 band)."""
    __tablename__ = "resolution_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(128), nullable=False, index=True)
    mention_a = Column(String(255), nullable=False)
    mention_b = Column(String(255), nullable=False)
    similarity = Column(Float, nullable=False)
    decision = Column(String(50), nullable=False)  # MERGED | PENDING_REVIEW | REJECTED
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClusterMembershipModel(Base):
    """Link between resolved cluster and source extracted entity (for graph)."""
    __tablename__ = "cluster_entity_membership"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(64), ForeignKey("entity_clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(Integer, ForeignKey("extracted_entities.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(String(128), ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"), nullable=False)

    cluster = relationship("ClusterModel", back_populates="memberships")


class ResolvedTripleModel(Base):
    """Relationship connecting two resolved clusters (graph edge)."""
    __tablename__ = "resolved_triples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(128), nullable=False, index=True)
    subject_cluster_id = Column(String(64), ForeignKey("entity_clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    predicate = Column(String(100), nullable=False)
    object_cluster_id = Column(String(64), ForeignKey("entity_clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    original_triple_id = Column(Integer, ForeignKey("extracted_triples.id", ondelete="SET NULL"), nullable=True)
    confidence = Column(Float, default=0.95)
    raw_timestamp = Column(String(100), nullable=True)
    raw_geo = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subject_cluster = relationship("ClusterModel", foreign_keys=[subject_cluster_id])
    object_cluster = relationship("ClusterModel", foreign_keys=[object_cluster_id])


class ClusterEvidenceSourceModel(Base):
    """Tracks which evidence documents contributed to each cluster."""
    __tablename__ = "cluster_evidence_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(64), ForeignKey("entity_clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(String(128), ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"), nullable=False)
    mention_count = Column(Integer, default=1)

    cluster = relationship("ClusterModel", back_populates="evidence_sources")


class ResolutionRepository:
    """Persist Agent 2 payloads to DB."""

    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def save_resolution(self, payload: ResolutionPayload) -> bool:
        """Insert clusters, pending_review, memberships, resolved triples, and evidence sources."""
        session = self.Session()
        try:
            # 1. Bulk upsert for clusters
            for cluster in payload.clusters:
                # Convert centroid embedding to JSON string if present
                centroid_json = None
                if cluster.centroid_embedding is not None:
                    centroid_json = json.dumps(cluster.centroid_embedding)

                stmt = pg_insert(ClusterModel).values(
                    run_id=payload.run_id,
                    cluster_id=cluster.cluster_id,
                    canonical_name=cluster.canonical,
                    entity_type=cluster.entity_type,
                    avg_similarity=cluster.avg_similarity,
                    member_count=len(cluster.members),
                    centroid_embedding=centroid_json,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["cluster_id"],
                    set_={
                        "run_id": stmt.excluded.run_id,
                        "canonical_name": stmt.excluded.canonical_name,
                        "entity_type": stmt.excluded.entity_type,
                        "avg_similarity": stmt.excluded.avg_similarity,
                        "member_count": stmt.excluded.member_count,
                        "centroid_embedding": stmt.excluded.centroid_embedding,
                    },
                )
                session.execute(stmt)

            # 2. Insert pending review pairs
            for pair in payload.pending_review:
                db_pair = ResolutionPairModel(
                    run_id=payload.run_id,
                    mention_a=pair.mention_a,
                    mention_b=pair.mention_b,
                    similarity=pair.similarity,
                    decision=pair.decision.value,
                )
                session.add(db_pair)

            # 3. Insert cluster-entity memberships (link cluster to source entities)
            cluster_entity_map = {}  # cluster_id -> set of entity_ids
            for cluster in payload.clusters:
                for member in cluster.members:
                    if member.entity_id is not None:
                        if cluster.cluster_id not in cluster_entity_map:
                            cluster_entity_map[cluster.cluster_id] = set()
                        if member.entity_id not in cluster_entity_map[cluster.cluster_id]:
                            cluster_entity_map[cluster.cluster_id].add(member.entity_id)
                            membership = ClusterMembershipModel(
                                cluster_id=cluster.cluster_id,
                                entity_id=member.entity_id,
                                evidence_id=member.evidence_id,
                            )
                            session.add(membership)

            # 4. Insert resolved triples (cluster relationships / graph edges)
            for triple in payload.resolved_triples:
                db_triple = ResolvedTripleModel(
                    run_id=payload.run_id,
                    subject_cluster_id=triple.subject_cluster_id,
                    predicate=triple.predicate,
                    object_cluster_id=triple.object_cluster_id,
                    original_triple_id=triple.original_triple_id,
                    confidence=triple.confidence,
                    raw_timestamp=triple.raw_timestamp,
                    raw_geo=triple.raw_geo,
                    latitude=triple.latitude,
                    longitude=triple.longitude,
                )
                session.add(db_triple)

            # 5. Insert evidence sources per cluster
            for source in payload.evidence_sources:
                # Check if already exists, update mention count if so
                existing = session.query(ClusterEvidenceSourceModel).filter_by(
                    cluster_id=source.cluster_id,
                    evidence_id=source.evidence_id,
                ).first()
                if existing:
                    existing.mention_count += source.mention_count
                else:
                    db_source = ClusterEvidenceSourceModel(
                        cluster_id=source.cluster_id,
                        evidence_id=source.evidence_id,
                        mention_count=source.mention_count,
                    )
                    session.add(db_source)

            session.commit()
            logger.info(
                f"Saved resolution '{payload.run_id}' to DB: "
                f"{len(payload.clusters)} clusters, {len(payload.resolved_triples)} triples"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save resolution: {e}")
            return False
        finally:
            session.close()

    def find_similar_clusters(
        self,
        embedding: list[float],
        entity_type: str = None,
        top_k: int = 5,
        threshold: float = 0.80,
    ) -> list[tuple[str, str, float]]:
        """
        Find existing clusters similar to the given embedding using pgvector cosine similarity.

        Args:
            embedding: 1024-dim BGE-m3 embedding (unit-norm)
            entity_type: Optional filter by entity_type
            top_k: Max number of results
            threshold: Min similarity score (cosine similarity, 0-1)

        Returns:
            List of (cluster_id, canonical_name, similarity_score) tuples
        """
        session = self.Session()
        try:
            from sqlalchemy import text
            embedding_json = json.dumps(embedding)

            # Build query with optional entity_type filter
            type_filter = "AND entity_type = :entity_type" if entity_type else ""

            query = text(f"""
                SELECT cluster_id, canonical_name, entity_type,
                       1 - (centroid_embedding <-> :embedding::vector) AS similarity
                FROM entity_clusters
                WHERE centroid_embedding IS NOT NULL
                {type_filter}
                AND (1 - (centroid_embedding <-> :embedding::vector)) >= :threshold
                ORDER BY centroid_embedding <-> :embedding::vector
                LIMIT :top_k
            """)

            params = {
                "embedding": embedding_json,
                "threshold": threshold,
                "top_k": top_k,
            }
            if entity_type:
                params["entity_type"] = entity_type

            result = session.execute(query, params)
            rows = result.fetchall()

            return [(row[0], row[1], float(row[3])) for row in rows]

        except Exception as e:
            logger.error(f"Vector similarity search failed: {e}")
            return []
        finally:
            session.close()