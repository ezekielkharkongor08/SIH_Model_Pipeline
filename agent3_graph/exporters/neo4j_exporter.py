"""
exporters/neo4j_exporter.py — Export knowledge graph to Neo4j database.
"""

from typing import List, Dict, Optional
from loguru import logger
from neo4j import GraphDatabase, Session
import uuid

from agent3_graph.models.schemas import KnowledgeGraph, GraphNode, GraphEdge
from agent3_graph.config import settings


class Neo4jExporter:
    """Export knowledge graph to Neo4j database."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def export_graph(self, graph: KnowledgeGraph) -> bool:
        """Export knowledge graph to Neo4j."""
        try:
            with self.driver.session() as session:
                # Clear previous graph data (optional, based on graph_id)
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
        MATCH (n:Entity {graph_id: $graph_id})
        DETACH DELETE n
        """
        session.run(query, graph_id=graph_id)

    def _create_node(self, session: Session, node: GraphNode, graph_id: str) -> str:
        """Create a node in Neo4j."""
        # Create main node
        create_query = """
        CREATE (n:Entity)
        SET n.node_id = $node_id,
            n.graph_id = $graph_id,
            n.canonical_name = $canonical_name,
            n.entity_type = $entity_type,
            n.confidence = $confidence,
            n.created_at = datetime(),
            n.labels = apoc.text.join([$entity_type], '_'),
            n.source_entity_count = size($source_entities),
            n.evidence_count = size($evidence_sources)
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

        # Create source entities as separate nodes connected to main node
        for entity_id in node.source_entities:
            source_query = """
            MATCH (main:Entity {node_id: $main_node_id, graph_id: $graph_id})
            MERGE (source:SourceEntity {entity_id: $entity_id, graph_id: $graph_id})
            SET source.type = 'source_entity',
                source.created_at = datetime()
            MERGE (main)-[:HAS_SOURCE_ENTITY]->(source)
            """
            session.run(
                source_query,
                main_node_id=node.node_id,
                graph_id=graph_id,
                entity_id=entity_id,
            )

        # Create evidence sources as separate nodes
        for evidence_id in node.evidence_sources:
            evidence_query = """
            MATCH (main:Entity {node_id: $main_node_id, graph_id: $graph_id})
            MERGE (evidence:Evidence {evidence_id: $evidence_id, graph_id: $graph_id})
            SET evidence.type = 'evidence',
                evidence.created_at = datetime()
            MERGE (main)-[:HAS_EVIDENCE]->(evidence)
            """
            session.run(
                evidence_query,
                main_node_id=node.node_id,
                graph_id=graph_id,
                evidence_id=evidence_id,
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
        """Create an edge (relationship) in Neo4j."""
        # Map node IDs (should be the same, but just in case)
        source_id = node_map.get(edge.source_node, edge.source_node)
        target_id = node_map.get(edge.target_node, edge.target_node)

        create_query = """
        MATCH (source:Entity {node_id: $source_id, graph_id: $graph_id})
        MATCH (target:Entity {node_id: $target_id, graph_id: $graph_id})
        CREATE (source)-[r:RELATION]->(target)
        SET r.edge_id = $edge_id,
            r.predicate = $predicate,
            r.confidence = $confidence,
            r.graph_id = $graph_id,
            r.is_predicted = $is_predicted,
            r.created_at = datetime(),
            r.original_triple_count = size($original_triples)
        """

        if edge.temporal:
            create_query += " SET r.temporal = $temporal"

        if edge.spatial:
            create_query += " SET r.spatial = $spatial"

        create_query += " RETURN r.edge_id as edge_id"

        params = {
            "source_id": source_id,
            "target_id": target_id,
            "graph_id": graph_id,
            "edge_id": edge.edge_id,
            "predicate": edge.predicate,
            "confidence": edge.confidence,
            "is_predicted": edge.is_predicted,
            "original_triples": edge.original_triples,
        }

        if edge.temporal:
            params["temporal"] = edge.temporal

        if edge.spatial:
            params["spatial"] = edge.spatial

        result = session.run(create_query, **params)

        record = result.single()
        return record["edge_id"] if record else edge.edge_id

    def _add_graph_metadata(self, session: Session, graph: KnowledgeGraph) -> None:
        """Add graph-level metadata to Neo4j."""
        query = """
        CREATE (g:KnowledgeGraph)
        SET g.graph_id = $graph_id,
            g.run_id = $run_id,
            g.node_count = $node_count,
            g.edge_count = $edge_count,
            g.created_at = $created_at,
            g.exported_at = datetime(),
            g.labels = ['KnowledgeGraph']
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
        """Query the exported graph in Neo4j."""
        try:
            with self.driver.session() as session:
                if query_type == "basic":
                    cypher = """
                    MATCH (n:Entity {graph_id: $graph_id})
                    RETURN n.node_id as node_id,
                           n.canonical_name as name,
                           n.entity_type as type,
                           n.confidence as confidence,
                           n.source_entity_count as source_count
                    ORDER BY n.entity_type, n.canonical_name
                    LIMIT 50
                    """
                elif query_type == "edges":
                    cypher = """
                    MATCH (s:Entity {graph_id: $graph_id})-[r:RELATION {graph_id: $graph_id}]->(t:Entity {graph_id: $graph_id})
                    RETURN s.node_id as source_id,
                           s.canonical_name as source_name,
                           r.predicate as relationship,
                           t.node_id as target_id,
                           t.canonical_name as target_name,
                           r.confidence as confidence
                    ORDER BY r.predicate
                    LIMIT 50
                    """
                elif query_type == "stats":
                    cypher = """
                    MATCH (g:KnowledgeGraph {graph_id: $graph_id})
                    RETURN g.graph_id as graph_id,
                           g.node_count as node_count,
                           g.edge_count as edge_count,
                           g.created_at as created_at,
                           g.exported_at as exported_at
                    """
                else:
                    cypher = """
                    MATCH (n:Entity {graph_id: $graph_id})
                    RETURN count(n) as node_count,
                           count{(n)-[]->()} as outbound_edges,
                           count{()-[]->(n)} as inbound_edges
                    """

                result = session.run(cypher, graph_id=graph_id)
                return [dict(record) for record in result]

        except Exception as e:
            logger.error(f"Neo4j query failed for graph {graph_id}: {e}")
            return []

    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()