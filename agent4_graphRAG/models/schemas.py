"""
models/schemas.py — Pydantic models for Agent 4 GraphRAG
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class GraphRAGQuery(BaseModel):
    """Natural language query to the knowledge graph."""
    query: str = Field(..., description="Natural language question about the graph")
    run_id: Optional[str] = Field(None, description="Filter by specific Agent 2 run ID")
    include_predictions: bool = Field(
        default=False,
        description="Include predicted edges in the search"
    )
    max_results: int = Field(
        default=10,
        description="Maximum number of results to return"
    )


class GraphRAGResult(BaseModel):
    """Result from a GraphRAG query."""
    answer: str = Field(..., description="Natural language answer to the query")
    confidence: float = Field(
        default=0.0,
        description="Confidence score of the answer (0-1)"
    )
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="List of evidence supporting the answer"
    )
    related_nodes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Nodes related to the query"
    )
    related_paths: List[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Graph paths related to the query"
    )
    query_time_ms: float = Field(
        default=0.0,
        description="Time taken to process the query"
    )


class GraphRAGStats(BaseModel):
    """Statistics about the GraphRAG system."""
    total_queries: int = 0
    avg_query_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    last_query_time: Optional[str] = None