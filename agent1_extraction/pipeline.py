import hashlib
import json
import time
from typing import Dict, List, Optional
from loguru import logger

from agent1_extraction.extraction.llm_extractor import UniversalLLMExtractor
from agent1_extraction.extraction.regex_extractor import DeterministicExtractor
from agent1_extraction.ingestion.parsers import UniversalInputParser
from agent1_extraction.models.schemas import (
    ExtractedEntity,
    ExtractedTriple,
    ExtractionPayload,
)
from agent1_extraction.normalization.normalizer import EntityNormalizer
from agent1_extraction.storage.database import DatabaseRepository
from agent1_extraction.verification.span_matcher import SpanVerifier


class UniversalExtractionPipeline:
  """Master Orchestrator for Agent 1 Multi-Format Extraction & Database Storage Platform."""

  def __init__(self):
    self.parser = UniversalInputParser()
    self.regex_extractor = DeterministicExtractor()
    self.llm_extractor = UniversalLLMExtractor()
    self.normalizer = EntityNormalizer()
    self.db_repo = DatabaseRepository()

  def process(
      self,
      evidence_id: Optional[str],
      raw_content: bytes,
      filename: str,
  ) -> ExtractionPayload:
    start_time = time.time()

    # 1. Compute Cryptographic Evidence Hash
    evidence_hash = hashlib.sha256(raw_content).hexdigest()

    # 2. Auto-generate a guaranteed unique evidence_id if omitted or placeholder
    if not evidence_id or evidence_id.strip() in [
        "",
        "string",
        "evidence_id",
        "None",
    ]:
      # Try extracting internal identifier from structured JSON
      try:
        parsed_json = json.loads(raw_content.decode("utf-8", errors="ignore"))
        if isinstance(parsed_json, dict) and "evidence_id" in parsed_json:
          evidence_id = str(parsed_json["evidence_id"])
      except Exception:
        pass

      # Fallback: Create unique ID (Filename + Epoch MS + Hash Prefix)
      if not evidence_id or evidence_id.strip() in [
          "",
          "string",
          "evidence_id",
          "None",
      ]:
        clean_filename = filename.split(".")[0].upper().replace("_", "-")
        timestamp_ms = int(time.time() * 1000)
        evidence_id = f"EV-{clean_filename}-{timestamp_ms}-{evidence_hash[:6]}"

    # 3. Universal Ingestion (Parses JSON, TXT, and Image with OCR Reconstruction)
    input_format, text_or_uri, direct_triples = self.parser.parse(
        raw_content, filename
    )

    # 4. Deterministic Regex Extraction
    regex_entities = self.regex_extractor.extract(text_or_uri)
    entity_registry: Dict[str, ExtractedEntity] = {
        e.canonical_name: e for e in regex_entities
    }

    # 5. LLM / RE Triple Extraction
    is_image_uri = text_or_uri.startswith("data:image")
    llm_triples = self.llm_extractor.extract_triples(
        text_or_uri, is_image=is_image_uri
    )
    all_raw_triples = direct_triples + llm_triples

    validated_triples: List[ExtractedTriple] = []

    # 6. Verification, Character Span Alignment & Predicate Cleaning
    for item in all_raw_triples:
      clean_sub = SpanVerifier.sanitize_entity_name(item.subject)
      clean_obj = SpanVerifier.sanitize_entity_name(item.object)

      if not clean_sub or not clean_obj:
        continue

      # Dynamic Predicate Sanitization (Strips object bleeding)
      clean_pred = SpanVerifier.sanitize_predicate(item.predicate, clean_obj)

      # Subject Entity Verification
      sub_span = SpanVerifier.find_span(text_or_uri, clean_sub)
      subject_entity = ExtractedEntity(
          canonical_name=clean_sub,
          entity_type=item.subject_type,
          span=sub_span,
      )
      entity_registry[clean_sub] = subject_entity

      # Object Entity Verification
      obj_span = SpanVerifier.find_span(text_or_uri, clean_obj)
      object_entity = ExtractedEntity(
          canonical_name=clean_obj,
          entity_type=item.object_type,
          span=obj_span,
      )
      entity_registry[clean_obj] = object_entity

      # Location Normalization
      norm_geo = None
      if item.location:
        norm_geo = self.normalizer.normalize_location(item.location)

      validated_triples.append(
          ExtractedTriple(
              subject=subject_entity,
              predicate=clean_pred,
              object=object_entity,
              raw_timestamp=item.timestamp,
              raw_geo=item.location,
              normalized_geo=norm_geo,
              confidence=0.95,
          )
      )

    execution_time = round((time.time() - start_time) * 1000, 2)

    # 7. Construct Final Verified Payload
    payload = ExtractionPayload(
        evidence_id=evidence_id,
        evidence_hash=evidence_hash,
        input_format=input_format,
        entities=list(entity_registry.values()),
        triples=validated_triples,
        execution_time_ms=execution_time,
        status="SUCCESS",
    )

    # 8. Persist Record and Triples to PostgreSQL
    try:
      self.db_repo.save_extraction(
          payload=payload, raw_text_content=text_or_uri
      )
    except Exception as e:
      logger.error(
          f"Failed to persist extraction payload '{evidence_id}' to DB: {e}"
      )

    return payload