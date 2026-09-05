"""
main_agent2.py — Standalone entry point for Agent 2 server
Runs the FastAPI server for entity resolution on port 8001.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent2_resolution.api.routes import router as resolution_router

app = FastAPI(
    title="SIH Agent 2 - Entity Resolution Engine",
    version="1.0.0",
    description="BGE-m3 embeddings + Metaphone blocking + Hierarchical Agglomerative Clustering",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resolution_router)


@app.get("/")
async def root():
    return {
        "status": "active",
        "service": "Agent 2 Entity Resolution Pipeline",
        "model": "BGE-m3",
        "thresholds": {
            "auto_merge": ">= 0.95",
            "pending_review": "0.80 - 0.94",
            "reject": "< 0.80",
        },
    }


if __name__ == "__main__":
    uvicorn.run("main_agent2:app", host="127.0.0.1", port=8001, reload=True)