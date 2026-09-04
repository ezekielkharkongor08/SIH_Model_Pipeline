import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. Import the router you built in routes.py
from agent1_extraction.api.routes import router as extraction_router

app = FastAPI(
    title="SIH Agent 1 - Universal Forensic Extraction Engine",
    version="2.0.0",
    description="Multi-format extraction API supporting JSON, Text, and Document Images.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Attach the external routes to the main application
app.include_router(extraction_router)

@app.get("/")
async def root():
  return {
      "status": "active",
      "service": "Agent 1 Universal Extraction Pipeline",
      "supported_formats": ["JSON", "TXT", "PNG", "JPG", "JPEG", "TIFF"],
  }

if __name__ == "__main__":
  uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)