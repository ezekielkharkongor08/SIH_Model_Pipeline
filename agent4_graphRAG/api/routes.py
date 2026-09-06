"""
api/routes.py — FastAPI routes for Agent 4 GraphRAG
Natural language query interface for the knowledge graph.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

from agent4_graphRAG.models.schemas import GraphRAGQuery, GraphRAGResult, GraphRAGStats
from agent4_graphRAG.storage.database import GraphRAGRepository


router = APIRouter(prefix="/api/v1/graphrag", tags=["GraphRAG Query Engine"])
repository = GraphRAGRepository()


# ── Request/Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Natural language query request."""
    query: str = Field(..., description="Natural language question", min_length=3)
    run_id: Optional[str] = Field(None, description="Filter by specific resolution run")
    include_predictions: bool = Field(
        default=False,
        description="Include predicted edges in results"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum results to return"
    )


class QueryResponse(BaseModel):
    """Response from GraphRAG query."""
    success: bool
    result: GraphRAGResult
    from_cache: bool = False
    message: str = "Query processed successfully"


# ── API Endpoints ───────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_graph(request: QueryRequest):
    """
    Query the knowledge graph using natural language.

    This endpoint:
    1. Extracts entities from the natural language query
    2. Searches the Neo4j knowledge graph for relevant nodes
    3. Finds relationships between matching nodes
    4. Generates a natural language answer with supporting evidence

    Example queries:
    - "Who works at TechCorp?"
    - "What is the relationship between Rajesh Sharma and Mumbai?"
    - "Show me all connections to Priya Malhotra"
    """
    try:
        logger.info(f"GraphRAG query received: {request.query[:100]}")

        # Create GraphRAG query object
        graph_query = GraphRAGQuery(
            query=request.query,
            run_id=request.run_id,
            include_predictions=request.include_predictions,
            max_results=request.max_results
        )

        # Execute query
        result_dict = repository.get_graph_context(graph_query)

        return QueryResponse(
            success=True,
            result=result_dict["context"],
            from_cache=result_dict.get("from_cache", False),
            message=f"Query processed in {result_dict['query_time_ms']:.1f}ms"
        )

    except Exception as e:
        logger.error(f"GraphRAG query failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )


@router.get("/query")
async def query_graph_get(
    q: str = Query(..., description="Natural language question", min_length=3),
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    include_predictions: bool = Query(False, description="Include predicted edges"),
    max_results: int = Query(10, ge=1, le=50, description="Max results")
):
    """
    Query the knowledge graph using natural language (GET endpoint).

    Same as POST /query but accessible via GET for simple testing.

    Example:
    GET /api/v1/graphrag/query?q=Who+works+at+TechCorp?
    """
    request = QueryRequest(
        query=q,
        run_id=run_id,
        include_predictions=include_predictions,
        max_results=max_results
    )
    return await query_graph(request)


@router.get("/stats", response_model=GraphRAGStats)
async def get_stats():
    """
    Get GraphRAG system statistics.

    Returns:
    - Total queries processed
    - Average query time
    - Cache hit/miss ratios
    """
    try:
        return repository.stats
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-cache")
async def clear_cache():
    """
    Clear the query cache.

    Forces all subsequent queries to be processed fresh from the database.
    """
    try:
        repository._query_cache.clear()
        logger.info("GraphRAG query cache cleared")
        return {
            "success": True,
            "message": "Query cache cleared successfully"
        }
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/examples")
async def get_examples():
    """
    Get example queries that can be used with the GraphRAG system.

    These examples demonstrate the types of natural language questions
    that can be answered using the knowledge graph.
    """
    return {
        "examples": [
            {
                "category": "Entity Lookup",
                "queries": [
                    "Who is Rajesh Sharma?",
                    "What do you know about TechCorp?",
                    "Tell me about Mumbai"
                ]
            },
            {
                "category": "Relationship Queries",
                "queries": [
                    "Who works at TechCorp?",
                    "What is the relationship between Rajesh and Priya?",
                    "Show connections between Mumbai and TechCorp"
                ]
            },
            {
                "category": "Path Finding",
                "queries": [
                    "How is Rajesh Sharma connected to Priya Malhotra?",
                    "Find paths between Mumbai and any person",
                    "What links TechCorp and Mumbai?"
                ]
            },
            {
                "category": "Aggregation",
                "queries": [
                    "How many people work at TechCorp?",
                    "List all organizations in Mumbai",
                    "Show all locations mentioned"
                ]
            }
        ],
        "tips": [
            "Use specific entity names for better results",
            "Include context words like 'works at', 'located in', etc.",
            "Try different phrasings if the first query doesn't work well",
            "Use include_predictions=true to see potential missing relationships"
        ]
    }


@router.get("/status")
async def get_status():
    """Health check endpoint for Agent 4 GraphRAG."""
    return {
        "status": "active",
        "agent": "Agent 4 - GraphRAG Query Engine",
        "description": "Natural language interface to the knowledge graph",
        "capabilities": [
            "Natural language queries to Neo4j knowledge graph",
            "Entity extraction from query text",
            "Path finding between entities",
            "Context retrieval for LLM processing",
            "Query caching for performance"
        ],
        "supported_queries": [
            "Entity lookup ('Who is X?')",
            "Relationship queries ('Who works at Y?')",
            "Path finding ('How is X connected to Y?')",
            "Aggregation ('How many X in Y?')"
        ],
        "cache_enabled": repository._query_cache is not None,
        "total_queries": repository.stats.total_queries
    }