from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class InputFormat(str, Enum):
  TEXT = "TEXT"
  JSON = "JSON"
  IMAGE = "IMAGE"


class EntityType(str, Enum):
  # Core Entities
  PERSON = "PERSON"
  ORGANIZATION = "ORGANIZATION"
  LOCATION = "LOCATION"
  PHONE_NUMBER = "PHONE_NUMBER"
  EMAIL = "EMAIL"
  DATE_TIME = "DATE_TIME"
  IDENTIFIER = "IDENTIFIER"

  # Legal & Procedural
  LAW_OFFENSE = "LAW_OFFENSE"
  LEGAL_SECTION = "LEGAL_SECTION"
  FIR_NUMBER = "FIR_NUMBER"
  CASE_NUMBER = "CASE_NUMBER"
  DOCUMENT = "DOCUMENT"
  ROLE = "ROLE"  # Suspect, Victim, Witness, Investigating Officer

  # Financial & Transactions
  BANK_ACCOUNT = "BANK_ACCOUNT"
  TRANSACTION_ID = "TRANSACTION_ID"
  MONEY_AMOUNT = "MONEY_AMOUNT"
  FINANCIAL_INSTRUMENT = "FINANCIAL_INSTRUMENT"
  UPI_ID = "UPI_ID"
  CRYPTO_WALLET = "CRYPTO_WALLET"

  # Digital & Cyber Forensics
  DEVICE = "DEVICE"  # Phones, laptops, hard drives
  SOFTWARE = "SOFTWARE"  # Malware, apps, platforms
  DIGITAL_ARTIFACT = "DIGITAL_ARTIFACT"  # IPs, URLs, MAC addresses, Hashes
  SOCIAL_MEDIA_HANDLE = "SOCIAL_MEDIA_HANDLE"

  # Physical & Forensic Evidence
  VEHICLE = "VEHICLE"
  WEAPON = "WEAPON"
  PROPERTY = "PROPERTY"
  NARCOTIC = "NARCOTIC"
  SUBSTANCE = "SUBSTANCE"
  PHYSICAL_EVIDENCE = "PHYSICAL_EVIDENCE"  # DNA, clothing, fingerprints
  INJURY_MEDICAL = "INJURY_MEDICAL"
  MEASUREMENT = "MEASUREMENT"

  # Context
  INCIDENT = "INCIDENT"
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
  source_document_id: Optional[str] = None

  @field_validator("subject_type", "object_type", mode="before")
  @classmethod
  def normalize_or_fallback_entity_type(cls, value: Any) -> Any:
    """Aggressive fail-safe validator for comprehensive edge cases."""
    if isinstance(value, str):
      val_clean = value.strip().upper().replace(" ", "_").replace("-", "_")

      synonym_map = {
          # Vehicles
          "CAR": EntityType.VEHICLE, "AUTOMOBILE": EntityType.VEHICLE, "TRUCK": EntityType.VEHICLE, 
          "BIKE": EntityType.VEHICLE, "MOTORCYCLE": EntityType.VEHICLE, "LICENSE_PLATE": EntityType.VEHICLE,
          "NUMBER_PLATE": EntityType.VEHICLE, "CHASSIS_NUMBER": EntityType.VEHICLE,
          
          # Weapons & Contraband
          "GUN": EntityType.WEAPON, "FIREARM": EntityType.WEAPON, "KNIFE": EntityType.WEAPON, 
          "AMMUNITION": EntityType.WEAPON, "PISTOL": EntityType.WEAPON,
          "DRUG": EntityType.NARCOTIC, "DRUGS": EntityType.NARCOTIC, "HEROIN": EntityType.NARCOTIC, 
          "COCAINE": EntityType.NARCOTIC, "POISON": EntityType.SUBSTANCE, "CHEMICAL": EntityType.SUBSTANCE,
          
          # Digital & Cyber
          "IP": EntityType.DIGITAL_ARTIFACT, "IP_ADDRESS": EntityType.DIGITAL_ARTIFACT, 
          "URL": EntityType.DIGITAL_ARTIFACT, "DOMAIN": EntityType.DIGITAL_ARTIFACT, 
          "MAC": EntityType.DIGITAL_ARTIFACT, "MAC_ADDRESS": EntityType.DIGITAL_ARTIFACT,
          "HASH": EntityType.DIGITAL_ARTIFACT, "MD5": EntityType.DIGITAL_ARTIFACT,
          "PHONE": EntityType.DEVICE, "MOBILE": EntityType.DEVICE, "SMARTPHONE": EntityType.DEVICE, 
          "LAPTOP": EntityType.DEVICE, "COMPUTER": EntityType.DEVICE, "HARD_DRIVE": EntityType.DEVICE,
          "APP": EntityType.SOFTWARE, "APPLICATION": EntityType.SOFTWARE, "MALWARE": EntityType.SOFTWARE,
          "TWITTER": EntityType.SOCIAL_MEDIA_HANDLE, "INSTAGRAM": EntityType.SOCIAL_MEDIA_HANDLE, 
          "FACEBOOK": EntityType.SOCIAL_MEDIA_HANDLE, "ACCOUNT": EntityType.SOCIAL_MEDIA_HANDLE,
          
          # Financial
          "CHEQUE": EntityType.FINANCIAL_INSTRUMENT, "CREDIT_CARD": EntityType.FINANCIAL_INSTRUMENT, 
          "DEBIT_CARD": EntityType.FINANCIAL_INSTRUMENT, "WALLET": EntityType.CRYPTO_WALLET, 
          "BTC_ADDRESS": EntityType.CRYPTO_WALLET, "CRYPTO": EntityType.CRYPTO_WALLET,
          "UPI": EntityType.UPI_ID, "VPA": EntityType.UPI_ID,
          
          # Law & Procedural
          "CRIME": EntityType.LAW_OFFENSE, "OFFENSE": EntityType.LAW_OFFENSE, "MURDER": EntityType.LAW_OFFENSE, 
          "THEFT": EntityType.LAW_OFFENSE, "FRAUD": EntityType.LAW_OFFENSE,
          "FIR": EntityType.FIR_NUMBER, "CASE": EntityType.CASE_NUMBER, "WARRANT": EntityType.DOCUMENT, 
          "PASSPORT": EntityType.DOCUMENT, "ID_CARD": EntityType.DOCUMENT, "AADHAAR": EntityType.IDENTIFIER,
          "PAN": EntityType.IDENTIFIER,
          
          # People Roles
          "SUSPECT": EntityType.ROLE, "VICTIM": EntityType.ROLE, "WITNESS": EntityType.ROLE, 
          "ACCUSED": EntityType.ROLE, "COMPLAINANT": EntityType.ROLE, "OFFICER": EntityType.ROLE,
          
          # Medical & Physical Evidence
          "INJURY": EntityType.INJURY_MEDICAL, "MEDICAL": EntityType.INJURY_MEDICAL, "WOUND": EntityType.INJURY_MEDICAL,
          "BLOOD": EntityType.PHYSICAL_EVIDENCE, "DNA": EntityType.PHYSICAL_EVIDENCE, 
          "FINGERPRINT": EntityType.PHYSICAL_EVIDENCE, "CLOTHING": EntityType.PHYSICAL_EVIDENCE,
          
          # Quantities
          "QUANTITY": EntityType.MEASUREMENT, "WEIGHT": EntityType.MEASUREMENT, "SPEED": EntityType.MEASUREMENT,
      }

      if val_clean in synonym_map:
        return synonym_map[val_clean]

      if val_clean in EntityType.__members__:
        return EntityType[val_clean]

      return EntityType.UNKNOWN

    return value


class RawLLMExtractionResponse(BaseModel):
  triples: List[RawTripleItem]