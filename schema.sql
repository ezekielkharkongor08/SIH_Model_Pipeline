-- PostgreSQL Schema Definition for Agent 1 Extraction Engine

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id VARCHAR(64) PRIMARY KEY,
    evidence_hash VARCHAR(64) NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extracted_entities (
    id SERIAL PRIMARY KEY,
    evidence_id VARCHAR(64) REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    start_char INT,
    end_char INT,
    exact_text TEXT,
    confidence FLOAT DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS extracted_triples (
    id SERIAL PRIMARY KEY,
    evidence_id VARCHAR(64) REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
    subject_name VARCHAR(255) NOT NULL,
    predicate VARCHAR(100) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    raw_timestamp VARCHAR(100),
    raw_geo TEXT,
    latitude FLOAT,
    longitude FLOAT,
    confidence FLOAT DEFAULT 0.95,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);