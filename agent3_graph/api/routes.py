"""
api/routes.py — FastAPI routes for Agent 3 Knowledge Graph Builder
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from loguru import logger

from agent3_graph.pipeline import KnowledgeGraphPipeline
from agent3_graph.models.schemas import KnowledgeGraph


router = APIRouter(prefix="/api/v1/graph", tags=["Knowledge Graph Builder"])
pipeline = KnowledgeGraphPipeline()


# ── Request/Response Models ─────────────────────────────────────────────────

class BuildGraphRequest(BaseModel):
    """Request to build a knowledge graph from Agent 2 resolution run."""
    run_id: str = Field(..., description="Agent 2 resolution run ID")
    export_formats: List[str] = Field(
        default=["json"],
        description="Export formats: ['json', 'neo4j', 'networkx']"
    )


class BuildGraphResponse(BaseModel):
    """Response from graph building."""
    success: bool
    graph_id: Optional[str] = None
    run_id: str
    statistics: dict
    exports: dict
    message: str


class GraphStatsResponse(BaseModel):
    """Graph statistics response."""
    graph_id: str
    node_count: int
    edge_count: int
    created_at: str
    networkx_stats: Optional[dict] = None


# ── API Endpoints ───────────────────────────────────────────────────────────

@router.post("/build", response_model=BuildGraphResponse)
async def build_graph(request: BuildGraphRequest):
    """
    Build a knowledge graph from Agent 2 resolution run.

    This is the manual/explicit endpoint - call it with a specific run_id
    to build a graph on-demand.
    """
    try:
        logger.info(f"Building knowledge graph for run_id: {request.run_id}")

        result = pipeline.build_and_export(
            run_id=request.run_id,
            export_formats=request.export_formats
        )

        return BuildGraphResponse(
            success=True,
            graph_id=result["graph_id"],
            run_id=result["run_id"],
            statistics=result["statistics"],
            exports=result["exports"],
            message=f"Knowledge graph built successfully: {result['graph_id']}"
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Graph building failed: {e}")
        raise HTTPException(status_code=500, detail=f"Graph building failed: {str(e)}")


@router.post("/auto-build", response_model=BuildGraphResponse)
async def auto_build_graph(request: BuildGraphRequest):
    """
    Auto-trigger endpoint for future pipeline integration.

    This endpoint can be called automatically by Agent 2 when
    AUTO_TRIGGER_GRAPH_BUILD is enabled in config.
    """
    try:
        logger.info(f"Auto-building knowledge graph for run_id: {request.run_id}")

        result = pipeline.build_and_export(
            run_id=request.run_id,
            export_formats=request.export_formats
        )

        return BuildGraphResponse(
            success=True,
            graph_id=result["graph_id"],
            run_id=result["run_id"],
            statistics=result["statistics"],
            exports=result["exports"],
            message=f"Knowledge graph auto-built successfully: {result['graph_id']}"
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Auto graph building failed: {e}")
        raise HTTPException(status_code=500, detail=f"Auto graph building failed: {str(e)}")


@router.get("/export/neo4j")
async def export_to_neo4j(
    run_id: str = Query(..., description="Agent 2 resolution run ID")
):
    """
    Build and export knowledge graph directly to Neo4j.

    Primary export format - exports to Neo4j database for graph queries.
    """
    try:
        logger.info(f"Exporting graph to Neo4j for run_id: {run_id}")

        # Build graph
        graph = pipeline.build_graph(run_id)

        # Export to Neo4j
        success = pipeline.export_to_neo4j(graph)

        if success:
            return {
                "success": True,
                "graph_id": graph.graph_id,
                "run_id": run_id,
                "message": f"Graph exported to Neo4j successfully",
                "neo4j_uri": "bolt://localhost:7687"
            }
        else:
            raise HTTPException(status_code=500, detail="Neo4j export failed")

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Neo4j export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Neo4j export failed: {str(e)}")


@router.get("/export/{format}")
async def export_graph(
    format: str,
    run_id: str = Query(..., description="Agent 2 resolution run ID")
):
    """
    Export knowledge graph to specified format.

    Supported formats: json, networkx, graphml
    """
    try:
        logger.info(f"Exporting graph to {format} for run_id: {run_id}")

        # Build graph
        graph = pipeline.build_graph(run_id)

        if format == "json":
            json_data = pipeline.export_as_json(graph)
            return JSONResponse(content=json_data, media_type="application/json")

        elif format == "networkx":
            nx_graph = pipeline.export_to_networkx(graph)
            if nx_graph:
                return {
                    "success": True,
                    "graph_id": graph.graph_id,
                    "format": "networkx",
                    "nodes": nx_graph.number_of_nodes(),
                    "edges": nx_graph.number_of_edges(),
                    "message": "Graph exported to NetworkX format (in-memory)"
                }
            else:
                raise HTTPException(status_code=500, detail="NetworkX export failed")

        elif format == "graphml":
            nx_graph = pipeline.export_to_networkx(graph)
            if nx_graph:
                from agent3_graph.exporters.networkx_exporter import NetworkxExporter
                exporter = NetworkxExporter()
                output_path = f"/tmp/graph_{graph.graph_id}.graphml"
                success = exporter.export_to_graphml(nx_graph, output_path)
                if success:
                    return {
                        "success": True,
                        "graph_id": graph.graph_id,
                        "format": "graphml",
                        "output_path": output_path,
                        "message": f"Graph exported to GraphML: {output_path}"
                    }
            raise HTTPException(status_code=500, detail="GraphML export failed")

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/stats")
async def get_graph_stats(
    run_id: Optional[str] = Query(None, description="Agent 2 resolution run ID"),
    graph_id: Optional[str] = Query(None, description="Knowledge graph ID"),
    include_networkx: bool = Query(False, description="Include NetworkX statistics")
):
    """
    Get statistics for a knowledge graph.

    Provide either run_id (to build new) or graph_id (to query existing).
    """
    try:
        if not run_id and not graph_id:
            raise HTTPException(status_code=400, detail="Must provide either run_id or graph_id")

        # Build graph if run_id provided
        if run_id:
            graph = pipeline.build_graph(run_id)
        else:
            # TODO: Implement graph retrieval by graph_id from database
            raise HTTPException(status_code=501, detail="Graph retrieval by graph_id not yet implemented")

        response_data = {
            "graph_id": graph.graph_id,
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "created_at": graph.created_at,
        }

        # Include NetworkX statistics if requested
        if include_networkx:
            nx_graph = pipeline.export_to_networkx(graph)
            if nx_graph:
                from agent3_graph.exporters.networkx_exporter import NetworkxExporter
                exporter = NetworkxExporter()
                networkx_stats = exporter.compute_statistics(nx_graph)
                response_data["networkx_stats"] = networkx_stats

        return response_data

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")


@router.get("/query/neighbors")
async def query_neighbors(
    run_id: str = Query(..., description="Agent 2 resolution run ID"),
    node_id: str = Query(..., description="Node ID to query neighbors for"),
    depth: int = Query(1, description="Depth of neighbor search (1-3)")
):
    """
    Query neighbors of a specific node in the knowledge graph.
    """
    try:
        if depth < 1 or depth > 3:
            raise HTTPException(status_code=400, detail="Depth must be between 1 and 3")

        # Build graph
        graph = pipeline.build_graph(run_id)

        # Export to NetworkX for querying
        nx_graph = pipeline.export_to_networkx(graph)

        if not nx_graph:
            raise HTTPException(status_code=500, detail="Failed to create NetworkX graph")

        # Query neighbors
        from agent3_graph.exporters.networkx_exporter import NetworkxExporter
        exporter = NetworkxExporter()
        neighbors = exporter.get_neighbors(nx_graph, node_id, depth=depth)

        return {
            "graph_id": graph.graph_id,
            "run_id": run_id,
            "query_node": node_id,
            "depth": depth,
            "neighbors": neighbors
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Neighbor query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Neighbor query failed: {str(e)}")


@router.get("/status")
async def get_status():
    """Health check endpoint for Agent 3."""
    return {
        "status": "active",
        "agent": "Agent 3 - Knowledge Graph Builder",
        "capabilities": [
            "Build knowledge graphs from Agent 1 & 2 data",
            "Export to Neo4j (primary)",
            "Export to NetworkX, JSON, GraphML",
            "Graph statistics and analysis",
            "Neighbor queries and path finding"
        ],
        "supported_formats": ["json", "neo4j", "networkx", "graphml"],
    }