"""
storage/database.py — Data access layer for Agent 3 Knowledge Graph Builder
Responsibility: Query Agent 1 & 2 data, store knowledge graph metadata.
"""

from typing import List, Dict, Optional, Tuple
from agent3_graph.config import settings
from agent3_graph.models.schemas import GraphNode, GraphEdge, KnowledgeGraph
from loguru import logger
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class KnowledgeGraphModel(Base):
    """Stores metadata about built knowledge graphs."""
    __tablename__ = "knowledge_graphs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    graph_id = Column(String(128), unique=True, nullable=False)
    run_id = Column(String(128), nullable=False)  # Links to Agent2's run_id
    node_count = Column(Integer, nullable=False)
    edge_count = Column(Integer, nullable=False)
    graph_data = Column(JSONB, nullable=True)  # Full graph structure for quick retrieval
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GraphRepository:
    """Repository for building knowledge graphs from Agent 1 & 2 data."""

    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def get_resolution_run(self, run_id: str) -> Dict[str, any]:
        """Get all data for a resolution run to build a knowledge graph."""
        session = self.Session()
        try:
            # 1. Get clusters from the run
            clusters_result = session.execute(text("""
                SELECT
                    cluster_id,
                    canonical_name,
                    entity_type,
                    avg_similarity as confidence,
                    member_count
                FROM entity_clusters
                WHERE run_id = :run_id
                ORDER BY entity_type, canonical_name
            """), {"run_id": run_id})
            clusters = clusters_result.fetchall()

            # 2. Get cluster-entity memberships (source entities)
            memberships_result = session.execute(text("""
                SELECT
                    cem.cluster_id,
                    cem.entity_id,
                    e.canonical_name,
                    e.entity_type,
                    e.evidence_id,
                    e.confidence
                FROM cluster_entity_membership cem
                JOIN extracted_entities e ON cem.entity_id = e.id
                WHERE cem.cluster_id IN (
                    SELECT cluster_id FROM entity_clusters WHERE run_id = :run_id
                )
                ORDER BY cem.cluster_id
            """), {"run_id": run_id})
            memberships = memberships_result.fetchall()

            # 3. Get resolved triples (graph edges)
            triples_result = session.execute(text("""
                SELECT
                    rt.subject_cluster_id,
                    rt.predicate,
                    rt.object_cluster_id,
                    rt.original_triple_id,
                    rt.confidence,
                    rt.raw_timestamp as temporal,
                    rt.raw_geo,
                    rt.latitude,
                    rt.longitude
                FROM resolved_triples rt
                WHERE rt.run_id = :run_id
                ORDER BY rt.predicate
            """), {"run_id": run_id})
            triples = triples_result.fetchall()

            # 4. Get evidence sources per cluster
            sources_result = session.execute(text("""
                SELECT
                    ces.cluster_id,
                    ces.evidence_id,
                    ces.mention_count,
                    er.input_format,
                    er.created_at
                FROM cluster_evidence_sources ces
                JOIN evidence_records er ON ces.evidence_id = er.evidence_id
                WHERE ces.cluster_id IN (
                    SELECT cluster_id FROM entity_clusters WHERE run_id = :run_id
                )
                ORDER BY ces.cluster_id
            """), {"run_id": run_id})
            sources = sources_result.fetchall()

            return {
                "clusters": clusters,
                "memberships": memberships,
                "triples": triples,
                "sources": sources,
                "run_id": run_id,
            }
        except Exception as e:
            logger.error(f"Failed to get resolution run data: {e}")
            return {"clusters": [], "memberships": [], "triples": [], "sources": []}
        finally:
            session.close()

    def build_knowledge_graph(self, run_id: str) -> KnowledgeGraph:
        """Build a knowledge graph from Agent 1 & 2 data."""
        import uuid
        from datetime import datetime

        # Get raw data
        data = self.get_resolution_run(run_id)
        if not data["clusters"]:
            raise ValueError(f"No resolution data found for run_id: {run_id}")

        # Build node map: cluster_id -> source_entity_ids, evidence_ids
        cluster_sources: Dict[str, Dict[str, List]] = {}
        for membership in data["memberships"]:
            cluster_id = membership[0]
            entity_id = membership[1]
            evidence_id = membership[4]

            if cluster_id not in cluster_sources:
                cluster_sources[cluster_id] = {"entity_ids": [], "evidence_ids": set()}

            cluster_sources[cluster_id]["entity_ids"].append(entity_id)
            cluster_sources[cluster_id]["evidence_ids"].add(evidence_id)

        # Build evidence source map: cluster_id -> evidence_ids (list)
        cluster_evidence: Dict[str, List[str]] = {}
        for source in data["sources"]:
            cluster_id = source[0]
            evidence_id = source[1]
            if cluster_id not in cluster_evidence:
                cluster_evidence[cluster_id] = []
            cluster_evidence[cluster_id].append(evidence_id)

        # Build nodes
        nodes: List[GraphNode] = []
        for cluster in data["clusters"]:
            cluster_id = cluster[0]
            sources = cluster_sources.get(cluster_id, {"entity_ids": [], "evidence_ids": set()})

            # Prefer evidence from cluster_evidence_sources table, fallback to membership table
            evidence_list = cluster_evidence.get(cluster_id) or list(sources["evidence_ids"])

            node = GraphNode(
                node_id=cluster_id,
                canonical_name=cluster[1],
                entity_type=cluster[2],
                source_entities=sources["entity_ids"],
                evidence_sources=evidence_list,
                confidence=cluster[3],
            )
            nodes.append(node)

        # Build edges
        edges: List[GraphEdge] = []
        edge_counter = 1
        for triple in data["triples"]:
            edge_id = f"EDGE-{run_id[:6]}-{edge_counter:04d}"
            edge_counter += 1

            original_triples = [triple[3]] if triple[3] else []

            spatial = None
            if triple[8] is not None and triple[9] is not None:
                spatial = {"latitude": triple[8], "longitude": triple[9]}

            edge = GraphEdge(
                edge_id=edge_id,
                source_node=triple[0],
                target_node=triple[2],
                predicate=triple[1],
                original_triples=original_triples,
                confidence=triple[4],
                temporal=triple[5],
                spatial=spatial,
            )
            edges.append(edge)

        # Create final graph
        graph_id = f"GRAPH-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now().isoformat()

        knowledge_graph = KnowledgeGraph(
            graph_id=graph_id,
            run_id=run_id,
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
            created_at=now_iso,
        )

        # Save graph metadata
        self.save_graph_metadata(knowledge_graph)

        return knowledge_graph

    def save_graph_metadata(self, graph: KnowledgeGraph) -> bool:
        """Save knowledge graph metadata to database."""
        session = self.Session()
        try:
            db_graph = KnowledgeGraphModel(
                graph_id=graph.graph_id,
                run_id=graph.run_id,
                node_count=graph.node_count,
                edge_count=graph.edge_count,
                graph_data=graph.dict(),  # Store full graph structure
            )
            session.add(db_graph)
            session.commit()
            logger.info(f"Saved knowledge graph '{graph.graph_id}' metadata")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save knowledge graph metadata: {e}")
            return False
        finally:
            session.close()