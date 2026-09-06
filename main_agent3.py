"""
main_agent3.py — Standalone FastAPI server for Agent 3 (Graph Builder Pro)
Runs on port 8002 for independent testing and development.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent3_graph.api.routes import router as graph_router

app = FastAPI(
    title="Agent 3 - Graph Builder Pro",
    version="1.0.0",
    description="Knowledge Graph Builder with Link Prediction (pgvector-enabled)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 3 knowledge graph routes
app.include_router(graph_router, prefix="")


@app.get("/")
async def root():
    return {
        "status": "active",
        "agent": "Agent 3 - Graph Builder Pro",
        "description": "Knowledge Graph Builder with optional Link Prediction",
        "features": [
            "Build knowledge graphs from Agent 2 resolution runs",
            "Link prediction using pgvector cosine similarity",
            "Export to Neo4j, NetworkX, JSON, GraphML",
            "Graph analytics and querying"
        ],
        "endpoints": {
            "docs": "/docs",
            "health": "/api/v1/graph/status",
            "build_graph": "POST /api/v1/graph/build",
            "export": "GET /api/v1/graph/export/{format}",
        },
    }


if __name__ == "__main__":
    uvicorn.run("main_agent3:app", host="127.0.0.1", port=8002, reload=True)
