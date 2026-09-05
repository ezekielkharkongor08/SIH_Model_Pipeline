"""
models/schemas.py — Pydantic models for Agent 3 Knowledge Graph Builder
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A node in the knowledge graph (resolved entity cluster)."""
    node_id: str = Field(..., description="Cluster ID from Agent 2 (e.g., 'CLU-00001')")
    canonical_name: str = Field(..., description="Canonical entity name")
    entity_type: str = Field(..., description="Entity type (PERSON, ORGANIZATION, etc.)")
    source_entities: List[int] = Field(
        default_factory=list,
        description="List of extracted entity IDs that belong to this cluster"
    )
    evidence_sources: List[str] = Field(
        default_factory=list,
        description="List of evidence IDs that contributed to this cluster"
    )
    confidence: float = Field(
        default=1.0,
        description="Average confidence of entities in this cluster"
    )


class GraphEdge(BaseModel):
    """An edge in the knowledge graph (relationship between clusters)."""
    edge_id: str = Field(..., description="Unique edge identifier")
    source_node: str = Field(..., description="Source cluster ID")
    target_node: str = Field(..., description="Target cluster ID")
    predicate: str = Field(..., description="Relationship type (e.g., 'works_for', 'located_in')")
    original_triples: List[int] = Field(
        default_factory=list,
        description="List of original triple IDs that support this edge"
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence of this relationship"
    )
    temporal: Optional[str] = Field(
        default=None,
        description="Temporal information (timestamp, date range)"
    )
    spatial: Optional[Dict[str, float]] = Field(
        default=None,
        description="Spatial information (e.g., {'latitude': 40.7128, 'longitude': -74.0060})"
    )


class KnowledgeGraph(BaseModel):
    """Complete knowledge graph structure."""
    graph_id: str = Field(..., description="Unique identifier for this graph build")
    run_id: str = Field(..., description="Agent 2 run ID that this graph is based on")
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")
    created_at: str = Field(..., description="Timestamp when graph was built")

    def get_node_by_id(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by its ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_edges_for_node(self, node_id: str) -> List[GraphEdge]:
        """Get all edges connected to a node."""
        return [
            edge for edge in self.edges
            if edge.source_node == node_id or edge.target_node == node_id
        ]

    def get_neighbors(self, node_id: str) -> List[str]:
        """Get neighbor node IDs."""
        neighbors = []
        for edge in self.edges:
            if edge.source_node == node_id:
                neighbors.append(edge.target_node)
            elif edge.target_node == node_id:
                neighbors.append(edge.source_node)
        return neighbors