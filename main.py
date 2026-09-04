from agent1_extraction.api.routes import router
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="SIH Agent 1 - Legal Forensic Extraction Pipeline",
    version="2.0.0",
    description=(
        "Deterministic entity extraction and triple generation engine with"
        " character span verification."
    ),
)

app.include_router(router)

if __name__ == "__main__":
  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)