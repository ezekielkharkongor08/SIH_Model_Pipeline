"""
main.py — Unified FastAPI server for SIH Agent 1 & Agent 2 & Agent 3 & Agent 4
Agent 1: Universal Forensic Extraction Engine
Agent 2: Entity Resolution Engine (BGE-m3 + HAC clustering)
Agent 3: Knowledge Graph Builder (with link prediction)
Agent 4: GraphRAG Query Engine (natural language interface)
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Agent 1 extraction routes
from agent1_extraction.api.routes import router as extraction_router

# Agent 2 resolution routes
from agent2_resolution.api.routes import router as resolution_router

# Agent 3 knowledge graph routes
from agent3_graph.api.routes import router as graph_router

# Agent 4 GraphRAG routes
from agent4_graphRAG.api.routes import router as graphrag_router

app = FastAPI(
    title="SIH Unified Extraction, Resolution, Graph & GraphRAG Engine",
    version="1.0.0",
    description=(
        "Agent 1: Extraction | "
        "Agent 2: Resolution | "
        "Agent 3: Knowledge Graph | "
        "Agent 4: GraphRAG Query"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 1: Extraction endpoints
app.include_router(extraction_router, prefix="/api/v1/extraction")

# Agent 2: Resolution endpoints
app.include_router(resolution_router, prefix="/api/v1/resolution")

# Agent 3: Knowledge Graph endpoints
app.include_router(graph_router, prefix="/api/v1/graph")

# Agent 4: GraphRAG Query endpoints
app.include_router(graphrag_router, prefix="")


@app.get("/")
async def root():
    return {
        "status": "active",
        "services": [
            "Agent 1 Extraction",
            "Agent 2 Resolution",
            "Agent 3 Graph Builder",
            "Agent 4 GraphRAG"
        ],
        "endpoints": {
            "extraction_docs": "/api/v1/extraction/docs",
            "resolution_docs": "/api/v1/resolution/docs",
            "graph_docs": "/api/v1/graph/docs",
            "graphrag_docs": "/api/v1/graphrag/docs",
        },
        "note": "All agents configured to read credentials from .env"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
