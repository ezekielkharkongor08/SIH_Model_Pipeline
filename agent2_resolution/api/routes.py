"""
routes.py — FastAPI routes for Agent 2 Entity Resolution API
"""

from typing import List
from fastapi import APIRouter, HTTPException
from loguru import logger

from agent2_resolution.models.schemas import ResolutionPayload, EntityMention
from agent2_resolution.pipeline import EntityResolutionPipeline
from agent1_extraction.models.schemas import ExtractionPayload

router = APIRouter(prefix="/api/v1/resolution", tags=["Entity Resolution Engine"])
pipeline = EntityResolutionPipeline()


@router.post("/resolve", response_model=ResolutionPayload)
async def resolve_extractions(
    payloads: List[ExtractionPayload]
):
    """
    Resolve entities across one or more Agent 1 extraction payloads.
    Direct integration endpoint: feed Agent 1's output directly here.
    """
    try:
        return pipeline.process(payloads)
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve-mentions", response_model=ResolutionPayload)
async def resolve_raw_mentions(
    mentions: List[EntityMention]
):
    """
    Resolve a flat list of entity mentions (useful for ad-hoc queries/testing).
    """
    try:
        return pipeline.resolve_mentions(mentions)
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    return {
        "status": "active",
        "agent": "Agent 2 - Entity Resolution",
        "embed_model": "BAAI/bge-m3",
        "thresholds": {
            "auto_merge": ">= 0.95",
            "pending_review": "0.80 - 0.94",
            "reject": "< 0.80",
        },
    }
