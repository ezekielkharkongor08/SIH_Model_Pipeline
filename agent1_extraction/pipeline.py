import hashlib
import json
import time
from typing import Dict, List, Optional
from agent1_extraction.extraction.llm_extractor import UniversalLLMExtractor
from agent1_extraction.extraction.regex_extractor import DeterministicExtractor
from agent1_extraction.ingestion.parsers import UniversalInputParser
from agent1_extraction.models.schemas import (
    ExtractedEntity,
    ExtractedTriple,
    ExtractionPayload,
)
from agent1_extraction.normalization.normalizer import EntityNormalizer
from agent1_extraction.verification.span_matcher import SpanVerifier


class UniversalExtractionPipeline:

  def __init__(self):
    self.parser = UniversalInputParser()  # Instantiated instance
    self.regex_extractor = DeterministicExtractor()
    self.llm_extractor = UniversalLLMExtractor()
    self.normalizer = EntityNormalizer()

  def process(
      self,
      evidence_id: Optional[str],
      raw_content: bytes,
      filename: str,
  ) -> ExtractionPayload:
    start_time = time.time()

    # 1. Compute Cryptographic Evidence Hash
    evidence_hash = hashlib.sha256(raw_content).hexdigest()

    # 2. Auto-generate evidence_id if omitted or left as placeholder
    if not evidence_id or evidence_id.strip() in [
        "",
        "string",
        "evidence_id",
        "None",
    ]:
      try:
        parsed_json = json.loads(raw_content.decode("utf-8", errors="ignore"))
        if isinstance(parsed_json, dict) and "evidence_id" in parsed_json:
          evidence_id = str(parsed_json["evidence_id"])
      except Exception:
        pass

      if not evidence_id or evidence_id.strip() in [
          "",
          "string",
          "evidence_id",
          "None",
      ]:
        clean_filename = filename.split(".")[0].upper().replace("_", "-")
        evidence_id = f"EV-{clean_filename}-{evidence_hash[:8]}"

    # 3. Universal Ingestion (Runs OCR + Text Reconstruction for Images)
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

    # 6. Verification & Character Span Alignment
    for item in all_raw_triples:
      clean_sub = SpanVerifier.sanitize_entity_name(item.subject)
      clean_obj = SpanVerifier.sanitize_entity_name(item.object)

      if not clean_sub or not clean_obj:
        continue

      sub_span = SpanVerifier.find_span(text_or_uri, clean_sub)
      subject_entity = ExtractedEntity(
          canonical_name=clean_sub,
          entity_type=item.subject_type,
          span=sub_span,
      )
      entity_registry[clean_sub] = subject_entity

      obj_span = SpanVerifier.find_span(text_or_uri, clean_obj)
      object_entity = ExtractedEntity(
          canonical_name=clean_obj,
          entity_type=item.object_type,
          span=obj_span,
      )
      entity_registry[clean_obj] = object_entity

      norm_geo = None
      if item.location:
        norm_geo = self.normalizer.normalize_location(item.location)

      validated_triples.append(
          ExtractedTriple(
              subject=subject_entity,
              predicate=item.predicate.strip().lower(),
              object=object_entity,
              raw_timestamp=item.timestamp,
              raw_geo=item.location,
              normalized_geo=norm_geo,
              confidence=0.95,
          )
      )

    execution_time = round((time.time() - start_time) * 1000, 2)

    return ExtractionPayload(
        evidence_id=evidence_id,
        evidence_hash=evidence_hash,
        input_format=input_format,
        entities=list(entity_registry.values()),
        triples=validated_triples,
        execution_time_ms=execution_time,
        status="SUCCESS",
    )