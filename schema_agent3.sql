-- schema_agent3.sql
-- Knowledge Graph storage tables for Agent 3
-- This stores metadata about built knowledge graphs

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