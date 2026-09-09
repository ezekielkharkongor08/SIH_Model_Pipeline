"""
models/schemas.py — Pydantic models for Agent 4 GraphRAG
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


class GraphRAGQuery(BaseModel):
    """Natural language query to the knowledge graph."""
    model_config = ConfigDict(extra="ignore")

    query: str = Field(..., min_length=1, description="Natural language question about the graph")
    run_id: Optional[str] = Field(None, description="Filter by specific Agent 2 run ID")
    include_predictions: bool = Field(default=False, description="Include predicted edges in search")
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")


class NodeDetail(BaseModel):
    """Structured representation of a graph node."""
    node_id: str
    canonical_name: str
    entity_type: str
    confidence: float = 1.0
    source_entities: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)

    @field_validator("source_entities", "evidence_sources", mode="before")
    @classmethod
    def coerce_elements_to_string(cls, v: Any) -> List[str]:
        """Ensure all elements in source/evidence lists are converted to strings."""
        if not isinstance(v, list):
            return []
        return [str(item) for item in v if item is not None]


class PathRelationship(BaseModel):
    """Structured representation of a graph relationship."""
    predicate: str
    confidence: float = 1.0
    is_predicted: bool = False


class PathDetail(BaseModel):
    """Structured representation of a path between nodes."""
    source: str
    target: str
    nodes: List[NodeDetail]
    relationships: List[PathRelationship]


class GraphRAGResult(BaseModel):
    """Result from a GraphRAG query."""
    answer: str = Field(..., description="Natural language answer to the query")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score (0-1)")
    supporting_evidence: List[str] = Field(default_factory=list)
    related_nodes: List[NodeDetail] = Field(default_factory=list)
    related_paths: List[PathDetail] = Field(default_factory=list)
    query_time_ms: float = Field(default=0.0, ge=0.0)


class GraphRAGStats(BaseModel):
    """Statistics about the GraphRAG system."""
    total_queries: int = 0
    avg_query_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    last_query_time: Optional[str] = None