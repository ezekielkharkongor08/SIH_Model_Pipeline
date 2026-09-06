import base64
import io
import json
import os
import re
from typing import Dict, List, Tuple
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import EntityType, InputFormat, RawTripleItem
import httpx
from loguru import logger
from PIL import Image
import pytesseract

if os.name == "nt":
  pytesseract.pytesseract.tesseract_cmd = (
      r"C:\Program Files\Tesseract-OCR\tesseract.exe"
  )


class UniversalInputParser:
  """Parses JSON, Plain Text, and Document Images into standardized text or explicit structural triples."""

  def _reconstruct_ocr_text(self, raw_ocr_text: str) -> str:
    prompt = f"""You are a document restoration expert. 
Clean up the following raw OCR text extracted from a scanned document.
Rules:
1. Fix broken words, OCR typos, and awkward line wraps.
2. Maintain all original facts, names, dates, numbers, and statements exactly.
3. Output ONLY the restored plain text narrative without introductory remarks or conversational responses.

Raw OCR Text:
{raw_ocr_text}
"""
    try:
      with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            json={
                "model": settings.LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        if response.status_code == 200:
          content = response.json()["choices"][0]["message"]["content"]
          return content.strip()
    except Exception as e:
      logger.warning(f"OCR text reconstruction bypassed: {e}")

    return raw_ocr_text.strip()

  def _parse_json(
      self, content: bytes
  ) -> Tuple[InputFormat, str, List[RawTripleItem]]:
    text_content = content.decode("utf-8", errors="ignore")
    direct_triples = []

    try:
      data = json.loads(text_content)
      if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        if (
            "subject" in data[0]
            and "predicate" in data[0]
            and "object" in data[0]
        ):
          for item in data:
            direct_triples.append(
                RawTripleItem(
                    subject=str(item.get("subject")),
                    subject_type=EntityType(
                        item.get("subject_type", EntityType.UNKNOWN)
                    ),
                    predicate=str(item.get("predicate")),
                    object=str(item.get("object")),
                    object_type=EntityType(
                        item.get("object_type", EntityType.UNKNOWN)
                    ),
                    timestamp=item.get("timestamp"),
                    location=item.get("location"),
                )
            )
          return InputFormat.JSON, json.dumps(data, indent=2), direct_triples

      lines = []
      if isinstance(data, dict):
        for k, v in data.items():
          lines.append(f"{k}: {v}")
      elif isinstance(data, list):
        for idx, row in enumerate(data):
          lines.append(f"Record {idx + 1}: {json.dumps(row)}")

      return InputFormat.JSON, "\n".join(lines), direct_triples
    except Exception as e:
      logger.warning(f"Failed to parse JSON content natively: {e}")
      return InputFormat.JSON, text_content, []

  def _parse_image(
      self, content: bytes
  ) -> Tuple[InputFormat, str, List[RawTripleItem]]:
    try:
      image = Image.open(io.BytesIO(content))
      raw_ocr_text = pytesseract.image_to_string(image)

      if raw_ocr_text.strip():
        logger.info(
            f"Raw Tesseract output: {len(raw_ocr_text)} chars. Reconstructing"
            " text..."
        )
        cleaned_text = self._reconstruct_ocr_text(raw_ocr_text)
        return InputFormat.IMAGE, cleaned_text, []
    except Exception as e:
      logger.warning(f"Local OCR execution failed: {e}")

    b64_image = base64.b64encode(content).decode("utf-8")
    return InputFormat.IMAGE, f"data:image/png;base64,{b64_image}", []

  def parse(
      self, raw_content: bytes, filename: str
  ) -> Tuple[InputFormat, str, List[RawTripleItem]]:
    """Main entrypoint for parsing file input."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext == "json":
      return self._parse_json(raw_content)
    elif ext in ["png", "jpg", "jpeg", "webp", "tiff"]:
      return self._parse_image(raw_content)
    else:
      # Default fallback to plain text parsing
      text = raw_content.decode("utf-8", errors="ignore")
      return InputFormat.TEXT, text, []