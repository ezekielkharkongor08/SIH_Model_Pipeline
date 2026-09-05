from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from agent1_extraction.models.schemas import ExtractionPayload
from agent1_extraction.pipeline import UniversalExtractionPipeline

# Initialize the router instead of the main app
router = APIRouter(prefix="/api/v1", tags=["Universal Extraction Engine"])
pipeline = UniversalExtractionPipeline()

@router.post("/extract", response_model=ExtractionPayload)
async def extract_document(
    file: UploadFile = File(..., description="File upload (JSON, TXT, or Image)"),
    evidence_id: Optional[str] = Form(default=None, description="Leave blank to auto-generate unique ID.")
):
    try:
        content = await file.read()
        return pipeline.process(
            evidence_id=evidence_id, raw_content=content, filename=file.filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))