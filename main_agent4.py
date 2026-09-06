"""
main_agent4.py — Standalone FastAPI server for Agent 4 (GraphRAG)
Runs on port 8003 for independent testing and development.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent4_graphRAG.api.routes import router as graphrag_router

app = FastAPI(
    title="Agent 4 - GraphRAG Query Engine",
    version="1.0.0",
    description="Natural language query interface for knowledge graphs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 4 GraphRAG routes
app.include_router(graphrag_router, prefix="")


@app.get("/")
async def root():
    return {
        "status": "active",
        "agent": "Agent 4 - GraphRAG Query Engine",
        "description": "Natural language interface to knowledge graphs",
        "features": [
            "Natural language queries to Neo4j",
            "Entity extraction from questions",
            "Path finding in knowledge graphs",
            "Query caching for performance",
            "Support for predicted edges"
        ],
        "endpoints": {
            "docs": "/docs",
            "health": "/api/v1/graphrag/status",
            "query_post": "POST /api/v1/graphrag/query",
            "query_get": "GET /api/v1/graphrag/query?q=your+question",
            "examples": "GET /api/v1/graphrag/examples",
            "stats": "GET /api/v1/graphrag/stats"
        },
        "example_usage": {
            "curl": 'curl -X POST "http://localhost:8003/api/v1/graphrag/query" -H "Content-Type: application/json" -d \'{"query": "Who works at TechCorp?"}\'',
            "browser": "http://localhost:8003/api/v1/graphrag/query?q=Who+works+at+TechCorp?"
        }
    }


if __name__ == "__main__":
    uvicorn.run("main_agent4:app", host="127.0.0.1", port=8003, reload=True)
