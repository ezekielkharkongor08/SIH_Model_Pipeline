"""
exporters/neo4j_exporter.py — Export knowledge graph to Neo4j database.
"""

from typing import List, Dict, Optional
import re
from loguru import logger
from neo4j import GraphDatabase, Session
import uuid

from agent3_graph.models.schemas import KnowledgeGraph, GraphNode, GraphEdge
from agent3_graph.config import settings


class Neo4jExporter:
    """Export knowledge graph to Neo4j database with strict property-based metadata."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def export_graph(self, graph: KnowledgeGraph) -> bool:
        """Export knowledge graph to Neo4j."""
        try:
            with self.driver.session() as session:
                # Clear previous graph data
                self._clear_graph(session, graph.graph_id)

                # Create nodes
                node_map = {}
                for node in graph.nodes:
                    node_id = self._create_node(session, node, graph.graph_id)
                    node_map[node.node_id] = node_id

                # Create edges
                for edge in graph.edges:
                    self._create_edge(session, edge, node_map, graph.graph_id)

                # Add graph metadata
                self._add_graph_metadata(session, graph)

                logger.info(
                    f"Exported graph '{graph.graph_id}' to Neo4j: "
                    f"{graph.node_count} nodes, {graph.edge_count} edges"
                )
                return True

        except Exception as e:
            logger.error(f"Neo4j export failed for graph {graph.graph_id}: {e}")
            return False

    def _clear_graph(self, session: Session, graph_id: str) -> None:
        """Clear existing graph data with the same graph_id."""
        query = """
        MATCH (n)
        WHERE n.graph_id = $graph_id
        DETACH DELETE n
        """
        session.run(query, graph_id=graph_id)

    def _create_node(self, session: Session, node: GraphNode, graph_id: str) -> str:
        """Create a node in Neo4j with metadata as properties, no metadata nodes."""
        create_query = """
        CREATE (n:Entity)
        SET n.node_id = $node_id,
            n.graph_id = $graph_id,
            n.canonical_name = $canonical_name,
            n.entity_type = $entity_type,
            n.confidence = $confidence,
            n.created_at = datetime(),
            n.source_doc_ids = $source_entities,
            n.evidence_ids = $evidence_sources
        RETURN n.node_id as node_id
        """

        result = session.run(
            create_query,
            node_id=node.node_id,
            graph_id=graph_id,
            canonical_name=node.canonical_name,
            entity_type=node.entity_type,
            confidence=node.confidence,
            source_entities=node.source_entities,
            evidence_sources=node.evidence_sources,
        )

        record = result.single()
        return record["node_id"] if record else node.node_id

    def _create_edge(
        self,
        session: Session,
        edge: GraphEdge,
        node_map: Dict[str, str],
        graph_id: str
    ) -> str:
        """Create a direct semantic edge (relationship) in Neo4j."""
        source_id = node_map.get(edge.source_node, edge.source_node)
        target_id = node_map.get(edge.target_node, edge.target_node)

        # Sanitize predicate to be a valid Neo4j relationship type
        safe_predicate = re.sub(r'[^A-Za-z0-9_]', '_', edge.predicate.upper())

        create_query = f"""
        MATCH (source:Entity {{node_id: $source_id, graph_id: $graph_id}})
        MATCH (target:Entity {{node_id: $target_id, graph_id: $graph_id}})
        CREATE (source)-[r:{safe_predicate}]->(target)
        SET r.edge_id = $edge_id,
            r.confidence = $confidence,
            r.graph_id = $graph_id,
            r.is_predicted = $is_predicted,
            r.created_at = datetime()
        """

        if edge.temporal:
            create_query += " SET r.temporal = $temporal"
        if edge.spatial:
            create_query += " SET r.spatial = $spatial"

        create_query += " RETURN elementId(r) as edge_id"

        params = {
            "source_id": source_id,
            "target_id": target_id,
            "graph_id": graph_id,
            "edge_id": edge.edge_id,
            "confidence": edge.confidence,
            "is_predicted": edge.is_predicted,
        }

        if edge.temporal:
            params["temporal"] = edge.temporal
        if edge.spatial:
            params["spatial"] = edge.spatial

        result = session.run(create_query, **params)
        record = result.single()
        return record["edge_id"] if record else edge.edge_id

    def _add_graph_metadata(self, session: Session, graph: KnowledgeGraph) -> None:
        """Add graph-level metadata to Neo4j as properties."""
        query = """
        CREATE (g:KnowledgeGraph)
        SET g.graph_id = $graph_id,
            g.run_id = $run_id,
            g.node_count = $node_count,
            g.edge_count = $edge_count,
            g.created_at = $created_at,
            g.exported_at = datetime()
        """
        session.run(
            query,
            graph_id=graph.graph_id,
            run_id=graph.run_id,
            node_count=graph.node_count,
            edge_count=graph.edge_count,
            created_at=graph.created_at,
        )

    def query_graph(self, graph_id: str, query_type: str = "basic") -> List[Dict]:
        """Query the exported graph in Neo4j (needs update to use new edge labels)."""
        # ... (implementation omitted for brevity, will need update for specific predicates)
        return []

    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()
