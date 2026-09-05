-- schema.sql

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id VARCHAR(128) PRIMARY KEY,
    evidence_hash VARCHAR(64) NOT NULL,
    input_format VARCHAR(20) NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extracted_entities (
    id SERIAL PRIMARY KEY,
    evidence_id VARCHAR(128) NOT NULL,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    start_char INTEGER,
    end_char INTEGER,
    exact_text TEXT,
    confidence FLOAT DEFAULT 1.0,

    CONSTRAINT fk_evidence_entity
        FOREIGN KEY (evidence_id)
        REFERENCES evidence_records(evidence_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extracted_triples (
    id SERIAL PRIMARY KEY,
    evidence_id VARCHAR(128) NOT NULL,
    subject_name VARCHAR(255) NOT NULL,
    subject_type VARCHAR(50) NOT NULL,
    predicate VARCHAR(100) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    object_type VARCHAR(50) NOT NULL,
    raw_timestamp VARCHAR(100),
    raw_geo TEXT,
    latitude FLOAT,
    longitude FLOAT,
    confidence FLOAT DEFAULT 0.95,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evidence_triple
        FOREIGN KEY (evidence_id)
        REFERENCES evidence_records(evidence_id)
        ON DELETE CASCADE
);