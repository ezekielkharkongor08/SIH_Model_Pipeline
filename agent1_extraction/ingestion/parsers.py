import base64
import csv
import io
import json
from typing import Dict, List, Tuple
from agent1_extraction.models.schemas import InputFormat, RawTripleItem, EntityType
from loguru import logger


class UniversalInputParser:
    """Parses arbitrary file formats (JSON, CSV, Text, Image) into standardized text or explicit structural triples."""

    @staticmethod
    def parse(raw_content: bytes, filename: str) -> Tuple[InputFormat, str, List[RawTripleItem]]:
        """
        Returns:
            - InputFormat
            - Normalized raw text representation for NLP/Span matching
            - Direct structural triples (if parsed natively from structured JSON/CSV)
        """
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        if ext == "json":
            return UniversalInputParser._parse_json(raw_content)
        elif ext in ["csv", "tsv"]:
            return UniversalInputParser._parse_csv(raw_content, is_tsv=(ext == "tsv"))
        elif ext in ["png", "jpg", "jpeg", "webp", "tiff"]:
            return UniversalInputParser._parse_image(raw_content)
        else:
            # Default fallback to plain text parsing
            text = raw_content.decode("utf-8", errors="ignore")
            return InputFormat.TEXT, text, []

    @staticmethod
    def _parse_json(content: bytes) -> Tuple[InputFormat, str, List[RawTripleItem]]:
        text_content = content.decode("utf-8", errors="ignore")
        direct_triples = []
        
        try:
            data = json.loads(text_content)
            
            # 1. Direct JSON Schema Triples (if pre-structured)
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                if "subject" in data[0] and "predicate" in data[0] and "object" in data[0]:
                    for item in data:
                        direct_triples.append(RawTripleItem(
                            subject=str(item.get("subject")),
                            subject_type=EntityType(item.get("subject_type", EntityType.UNKNOWN)),
                            predicate=str(item.get("predicate")),
                            object=str(item.get("object")),
                            object_type=EntityType(item.get("object_type", EntityType.UNKNOWN)),
                            timestamp=item.get("timestamp"),
                            location=item.get("location")
                        ))
                    return InputFormat.JSON, json.dumps(data, indent=2), direct_triples

            # 2. Key-Value or Arbitrary JSON structure -> Convert to narrative text representation
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

    @staticmethod
    def _parse_csv(content: bytes, is_tsv: bool = False) -> Tuple[InputFormat, str, List[RawTripleItem]]:
        text_content = content.decode("utf-8", errors="ignore")
        delimiter = "\t" if is_tsv else ","
        reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
        
        lines = []
        rows = list(reader)
        if not rows:
            return InputFormat.CSV, "", []

        headers = rows[0]
        for row_idx, row in enumerate(rows[1:], start=1):
            row_str = ", ".join([f"{headers[i]}: {val}" for i, val in enumerate(row) if i < len(headers)])
            lines.append(f"Row {row_idx}: {row_str}")

        formatted_text = "\n".join(lines)
        return InputFormat.CSV, formatted_text, []

    @staticmethod
    def _parse_image(content: bytes) -> Tuple[InputFormat, str, List[RawTripleItem]]:
        """Encodes image content to base64 string for direct Multimodal Vision LLM execution."""
        b64_image = base64.b64encode(content).decode("utf-8")
        # Format payload specifically as image URI for multimodal models
        image_uri = f"data:image/png;base64,{b64_image}"
        return InputFormat.IMAGE, image_uri, []