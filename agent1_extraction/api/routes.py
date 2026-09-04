from typing import Optional
from agent1_extraction.models.schemas import ExtractionPayload
from agent1_extraction.pipeline import UniversalExtractionPipeline
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/v1", tags=["Universal Extraction Engine"])
pipeline = UniversalExtractionPipeline()


@router.post("/extract", response_model=ExtractionPayload)
async def extract_file(
    file: UploadFile = File(...),
    evidence_id: Optional[str] = Form(
        None, description="Optional. Auto-generated if left blank."
    ),
):
  try:
    content = await file.read()
    payload = pipeline.process(
        evidence_id=evidence_id, raw_content=content, filename=file.filename
    )
    return payload
  except Exception as e:
    raise HTTPException(
        status_code=500, detail=f"Universal extraction error: {str(e)}"
    )