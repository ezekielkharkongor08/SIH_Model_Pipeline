from sqlalchemy import Column, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import ExtractionPayload

Base = declarative_base()


class EvidenceModel(Base):
  __tablename__ = "evidence_records"
  evidence_id = Column(String(64), primary_key=True)
  evidence_hash = Column(String(64), nullable=False)
  raw_text = Column(Text, nullable=False)


class TripleModel(Base):
  __tablename__ = "extracted_triples"
  id = Column(Integer, primary_key=True, autoincrement=True)
  evidence_id = Column(String(64), nullable=False)
  subject_name = Column(String(255), nullable=False)
  predicate = Column(String(100), nullable=False)
  object_name = Column(String(255), nullable=False)
  raw_timestamp = Column(String(100), nullable=True)
  raw_geo = Column(Text, nullable=True)
  latitude = Column(Float, nullable=True)
  longitude = Column(Float, nullable=True)


class DatabaseRepository:

  def __init__(self):
    self.engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    self.Session = sessionmaker(bind=self.engine)

  def save_payload(self, raw_text: str, payload: ExtractionPayload) -> bool:
    try:
      # Auto-create tables if they do not exist
      Base.metadata.create_all(self.engine)
      session = self.Session()

      evidence = EvidenceModel(
          evidence_id=payload.evidence_id,
          evidence_hash=payload.evidence_hash,
          raw_text=raw_text,
      )
      session.merge(evidence)

      for t in payload.triples:
        db_triple = TripleModel(
            evidence_id=payload.evidence_id,
            subject_name=t.subject.canonical_name,
            predicate=t.predicate,
            object_name=t.object.canonical_name,
            raw_timestamp=t.raw_timestamp,
            raw_geo=t.raw_geo,
            latitude=t.normalized_geo.latitude if t.normalized_geo else None,
            longitude=t.normalized_geo.longitude if t.normalized_geo else None,
        )
        session.add(db_triple)

      session.commit()
      session.close()
      return True
    except Exception:
      return False