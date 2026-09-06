-- schema_agent2.sql
-- Entity resolution tables for Agent 2 (BGE-m3 + HAC clustering + pgvector)
-- This complements the base evidence and extraction tables in schema.sql
-- Enables connected knowledge graph with full entity-to-cluster-to-relationship traceability
-- pgvector integration for embedding storage and similarity search

-- ═══════════════════════════════════════════════════════════════════════════════
-- PGVECTOR SETUP
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══════════════════════════════════════════════════════════════════════════════
-- CORE RESOLUTION TABLES
-- ═══════════════════════════════════════════════════════════════════════════════

-- Resolved entity clusters (final canonical entities) with pgvector embeddings
CREATE TABLE IF NOT EXISTS entity_clusters (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    cluster_id VARCHAR(64) UNIQUE NOT NULL,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    avg_similarity FLOAT NOT NULL,
    member_count INTEGER NOT NULL,
    centroid_embedding VECTOR(1024),  -- BGE-m3 centroid embedding (unit-norm)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_clusters_run_id (run_id),
    INDEX idx_clusters_entity_type (entity_type)
);

-- HNSW index for fast cosine similarity search on centroid embeddings
-- Uses cosine distance (<-> operator) for similarity ranking
CREATE INDEX IF NOT EXISTS idx_clusters_centroid_hnsw
ON entity_clusters
USING hnsw (centroid_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Pending resolution decisions (requires human/LLM review)
CREATE TABLE IF NOT EXISTS resolution_decisions (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    mention_a VARCHAR(255) NOT NULL,
    mention_b VARCHAR(255) NOT NULL,
    similarity FLOAT NOT NULL,
    decision VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_decisions_run_id (run_id),
    INDEX idx_decisions_decision (decision)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- GRAPH RELATIONSHIP TABLES (for connected knowledge graph)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Link resolved clusters back to source entities (cluster membership)
CREATE TABLE IF NOT EXISTS cluster_entity_membership (
    id SERIAL PRIMARY KEY,
    cluster_id VARCHAR(64) NOT NULL,
    entity_id INTEGER NOT NULL,
    evidence_id VARCHAR(128) NOT NULL,

    CONSTRAINT fk_cluster_membership
        FOREIGN KEY (cluster_id)
        REFERENCES entity_clusters(cluster_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_entity_membership
        FOREIGN KEY (entity_id)
        REFERENCES extracted_entities(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_membership
        FOREIGN KEY (evidence_id)
        REFERENCES evidence_records(evidence_id)
        ON DELETE CASCADE,

    UNIQUE(cluster_id, entity_id),
    INDEX idx_membership_cluster (cluster_id),
    INDEX idx_membership_entity (entity_id),
    INDEX idx_membership_evidence (evidence_id)
);

-- Links resolved entity clusters through predicates (graph edges)
-- This enables querying: "Which clusters are connected and through what relationship?"
CREATE TABLE IF NOT EXISTS resolved_triples (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    subject_cluster_id VARCHAR(64) NOT NULL,
    predicate VARCHAR(100) NOT NULL,
    object_cluster_id VARCHAR(64) NOT NULL,
    original_triple_id INTEGER,
    confidence FLOAT DEFAULT 0.95,
    raw_timestamp VARCHAR(100),
    raw_geo TEXT,
    latitude FLOAT,
    longitude FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_subject_cluster
        FOREIGN KEY (subject_cluster_id)
        REFERENCES entity_clusters(cluster_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_object_cluster
        FOREIGN KEY (object_cluster_id)
        REFERENCES entity_clusters(cluster_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_original_triple
        FOREIGN KEY (original_triple_id)
        REFERENCES extracted_triples(id)
        ON DELETE SET NULL,

    INDEX idx_resolved_triples_subject (subject_cluster_id),
    INDEX idx_resolved_triples_object (object_cluster_id),
    INDEX idx_resolved_triples_predicate (predicate),
    INDEX idx_resolved_triples_run (run_id)
);

-- Tracks which evidence documents contributed to each cluster
-- This enables querying: "Where did this resolved entity come from?"
CREATE TABLE IF NOT EXISTS cluster_evidence_sources (
    id SERIAL PRIMARY KEY,
    cluster_id VARCHAR(64) NOT NULL,
    evidence_id VARCHAR(128) NOT NULL,
    mention_count INTEGER DEFAULT 1,

    CONSTRAINT fk_cluster_source
        FOREIGN KEY (cluster_id)
        REFERENCES entity_clusters(cluster_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_source
        FOREIGN KEY (evidence_id)
        REFERENCES evidence_records(evidence_id)
        ON DELETE CASCADE,

    UNIQUE(cluster_id, evidence_id),
    INDEX idx_cluster_evidence_cluster (cluster_id),
    INDEX idx_cluster_evidence_source (evidence_id)
);