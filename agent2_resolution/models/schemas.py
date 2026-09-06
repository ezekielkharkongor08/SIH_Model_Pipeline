from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Decision labels ───────────────────────────────────────────────────────────

class ResolutionDecision(str, Enum):
    MERGED = "MERGED"               # similarity >= 0.95 → same entity
    PENDING_REVIEW = "PENDING_REVIEW"  # 0.80–0.94 → human / stub review
    REJECTED = "REJECTED"           # < 0.80 → distinct entities, no merge


# ── Per-entity mention (thin wrapper around Agent 1's entity fields) ──────────

class EntityMention(BaseModel):
    """A single entity surface as extracted by Agent 1."""
    surface: str = Field(..., description="canonical_name from Agent 1")
    entity_type: str
    evidence_id: str                # which document this came from
    confidence: float = 1.0
    entity_id: Optional[int] = None  # FK to extracted_entities.id (for graph linking)


# ── Cluster produced by HAC ───────────────────────────────────────────────────

class EntityCluster(BaseModel):
    """One resolved entity — all mentions that refer to the same real-world node."""
    cluster_id: str                  # e.g. "CLU-00001"
    canonical: str                   # elected representative name
    entity_type: str
    members: List[EntityMention]     # all surface mentions in this cluster
    avg_similarity: float            # intra-cluster mean pairwise similarity
    centroid_embedding: Optional[List[float]] = None  # 1024-dim BGE-m3 centroid (unit-norm)


# ── Per-pair resolution decision ──────────────────────────────────────────────

class ResolutionPair(BaseModel):
    """Result for one (mention_a, mention_b) comparison."""
    mention_a: str
    mention_b: str
    similarity: float
    decision: ResolutionDecision


# ── Resolved graph structures (for Agent 3 graph building) ───────────────────

class ResolvedTriple(BaseModel):
    """A relationship connecting two resolved clusters (graph edge)."""
    subject_cluster_id: str
    predicate: str
    object_cluster_id: str
    original_triple_id: Optional[int] = None
    confidence: float = 0.95
    raw_timestamp: Optional[str] = None
    raw_geo: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ClusterEvidenceSource(BaseModel):
    """Evidence source tracking for a cluster."""
    cluster_id: str
    evidence_id: str
    mention_count: int = 1


# ── Top-level output of Agent 2 ───────────────────────────────────────────────

class ResolutionPayload(BaseModel):
    run_id: str                      # auto-generated UUID per resolution run
    evidence_ids: List[str]          # which Agent 1 evidence batches were processed
    clusters: List[EntityCluster]
    pending_review: List[ResolutionPair]   # 0.80–0.94 band, routed for review
    resolved_triples: List[ResolvedTriple] = []  # NEW: Connected graph edges
    evidence_sources: List[ClusterEvidenceSource] = []  # NEW: Evidence tracking
    total_mentions: int
    total_clusters: int
    total_triples: int = 0
    execution_time_ms: float
    status: str = "SUCCESS"
    execution_time_ms: float
    status: str = "SUCCESS"
