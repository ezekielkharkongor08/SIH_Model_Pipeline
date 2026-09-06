-- schema_agent3.sql
-- Knowledge Graph storage tables for Agent 3 (Graph Builder Pro)
-- Includes link prediction support using pgvector from Agent 2

-- Knowledge Graph metadata table
CREATE TABLE IF NOT EXISTS knowledge_graphs (
    id SERIAL PRIMARY KEY,
    graph_id VARCHAR(128) UNIQUE NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    graph_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_graphs_run_id (run_id),
    INDEX idx_graphs_graph_id (graph_id)
);

-- Note: Agent 3 link prediction uses the centroid_embedding column
-- from entity_clusters table (defined in schema_agent2.sql).
-- No additional tables needed for link prediction feature.