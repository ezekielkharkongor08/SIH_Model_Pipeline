from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InputFormat(str, Enum):
  TEXT = "TEXT"
  JSON = "JSON"
  IMAGE = "IMAGE"


class EntityType(str, Enum):
  PERSON = "PERSON"
  ORGANIZATION = "ORGANIZATION"
  LOCATION = "LOCATION"
  PHONE_NUMBER = "PHONE_NUMBER"
  EMAIL = "EMAIL"
  BANK_ACCOUNT = "BANK_ACCOUNT"
  TRANSACTION_ID = "TRANSACTION_ID"
  MONEY_AMOUNT = "MONEY_AMOUNT"
  DATE_TIME = "DATE_TIME"
  IDENTIFIER = "IDENTIFIER"
  LEGAL_SECTION = "LEGAL_SECTION"
  UNKNOWN = "UNKNOWN"


class CharacterSpan(BaseModel):
  start_char: int
  end_char: int
  exact_text: str


class NormalizedGeo(BaseModel):
  raw_location: str
  formatted_address: Optional[str] = None
  latitude: Optional[float] = None
  longitude: Optional[float] = None


class ExtractedEntity(BaseModel):
  canonical_name: str = Field(
      ..., description="Clean entity name or value without surrounding noise"
  )
  entity_type: EntityType
  span: Optional[CharacterSpan] = None
  confidence: float = 1.0


class ExtractedTriple(BaseModel):
  subject: ExtractedEntity
  predicate: str = Field(
      ..., description="Relationship in snake_case (e.g., works_for, transferred_to)"
  )
  object: ExtractedEntity
  evidence_span: Optional[CharacterSpan] = None
  raw_timestamp: Optional[str] = None
  normalized_timestamp: Optional[str] = None
  raw_geo: Optional[str] = None
  normalized_geo: Optional[NormalizedGeo] = None
  confidence: float = 0.95


class ExtractionPayload(BaseModel):
  evidence_id: str
  evidence_hash: str
  input_format: InputFormat
  entities: List[ExtractedEntity]
  triples: List[ExtractedTriple]
  execution_time_ms: float
  status: str = "SUCCESS"


class RawTripleItem(BaseModel):
  subject: str
  subject_type: EntityType
  predicate: str
  object: str
  object_type: EntityType
  timestamp: Optional[str] = None
  location: Optional[str] = None


class RawLLMExtractionResponse(BaseModel):
  triples: List[RawTripleItem]