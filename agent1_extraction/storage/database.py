from typing import Optional
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import ExtractionPayload
from loguru import logger
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class EvidenceModel(Base):
  __tablename__ = "evidence_records"
  evidence_id = Column(String(128), primary_key=True)
  evidence_hash = Column(String(64), nullable=False)
  input_format = Column(String(20), nullable=False)
  raw_text = Column(Text, nullable=False)
  created_at = Column(DateTime(timezone=True), server_default=func.now())
  
  # ORM Relationships (allows accessing child records directly from Python)
  entities = relationship("EntityModel", backref="evidence", cascade="all, delete-orphan")
  triples = relationship("TripleModel", backref="evidence", cascade="all, delete-orphan")


class EntityModel(Base):
  __tablename__ = "extracted_entities"
  id = Column(Integer, primary_key=True, autoincrement=True)
  # Added explicit Foreign Key
  evidence_id = Column(String(128), ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"), nullable=False)
  canonical_name = Column(String(255), nullable=False)
  entity_type = Column(String(50), nullable=False)
  start_char = Column(Integer, nullable=True)
  end_char = Column(Integer, nullable=True)
  exact_text = Column(Text, nullable=True)
  confidence = Column(Float, default=1.0)


class TripleModel(Base):
  __tablename__ = "extracted_triples"
  id = Column(Integer, primary_key=True, autoincrement=True)
  # Added explicit Foreign Key
  evidence_id = Column(String(128), ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"), nullable=False)
  subject_name = Column(String(255), nullable=False)
  subject_type = Column(String(50), nullable=False)
  predicate = Column(String(100), nullable=False)
  object_name = Column(String(255), nullable=False)
  object_type = Column(String(50), nullable=False)
  raw_timestamp = Column(String(100), nullable=True)
  raw_geo = Column(Text, nullable=True)
  latitude = Column(Float, nullable=True)
  longitude = Column(Float, nullable=True)
  confidence = Column(Float, default=0.95)


class DatabaseRepository:

  def __init__(self):
    self.engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    self.Session = sessionmaker(bind=self.engine)
    Base.metadata.create_all(self.engine)

  def save_extraction(
      self, payload: ExtractionPayload, raw_text_content: str
  ) -> bool:
    session = self.Session()
    try:
      evidence_record = EvidenceModel(
          evidence_id=payload.evidence_id,
          evidence_hash=payload.evidence_hash,
          input_format=payload.input_format,
          raw_text=raw_text_content,
      )
      session.merge(evidence_record)

      for entity in payload.entities:
        db_entity = EntityModel(
            evidence_id=payload.evidence_id,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            start_char=entity.span.start_char if entity.span else None,
            end_char=entity.span.end_char if entity.span else None,
            exact_text=entity.span.exact_text if entity.span else None,
            confidence=entity.confidence,
        )
        session.add(db_entity)

      for triple in payload.triples:
        db_triple = TripleModel(
            evidence_id=payload.evidence_id,
            subject_name=triple.subject.canonical_name,
            subject_type=triple.subject.entity_type,
            predicate=triple.predicate,
            object_name=triple.object.canonical_name,
            object_type=triple.object.entity_type,
            raw_timestamp=triple.raw_timestamp,
            raw_geo=triple.raw_geo,
            latitude=(triple.normalized_geo.latitude if triple.normalized_geo else None),
            longitude=(triple.normalized_geo.longitude if triple.normalized_geo else None),
            confidence=triple.confidence,
        )
        session.add(db_triple)

      session.commit()
      return True
    except Exception as e:
      session.rollback()
      logger.error(f"Database transaction failed for '{payload.evidence_id}': {e}")
      return False
    finally:
      session.close()