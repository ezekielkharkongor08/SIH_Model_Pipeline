import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from agent1_extraction.models.schemas import ExtractionPayload
from agent1_extraction.pipeline import UniversalExtractionPipeline

app = FastAPI(
    title="SIH Agent 1 - Universal Forensic Extraction Engine",
    version="2.0.0",
    description="Multi-format extraction API supporting JSON, CSV, Text, and Document Images.",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = UniversalExtractionPipeline()


@app.get("/")
async def root():
  return {
      "status": "active",
      "service": "Agent 1 Universal Extraction Pipeline",
      "supported_formats": ["JSON", "TXT", "PNG", "JPG", "JPEG", "TIFF"],
  }


@app.post("/api/v1/extract", response_model=ExtractionPayload)
async def extract_document(
    evidence_id: str = Form(..., description="Unique Evidence Identifier"),
    file: UploadFile = File(..., description="File upload (JSON, CSV, TXT, or Image)")
):
    """
    Universal Extraction Endpoint:
    Uploads evidence file, computes cryptographic hash, executes extraction pipeline,
    and returns verified triples with character spans.
    """
    try:
        content = await file.read()
        payload = pipeline.process(
            evidence_id=evidence_id,
            raw_content=content,
            filename=file.filename
        )
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed for file {file.filename}: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)