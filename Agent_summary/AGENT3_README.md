# Agent 3 - Graph Builder Pro (Knowledge Graph + Link Prediction)

## Overview

Agent 3 is the **Knowledge Graph Builder** that takes entity clusters from Agent 2 and builds a queryable knowledge graph. It now includes **Link Prediction** as an optional feature, using BGE-m3 centroid embeddings from pgvector to predict missing relationships between entities.

**Core Features:**
- Build knowledge graphs from Agent 2 resolved clusters
- Optional link prediction using vector similarity (Agent 4 merged)
- Export to Neo4j, NetworkX, JSON, and GraphML
- Graph analytics: neighbors, paths, statistics

## Architecture

```
agent3_graph/
├── config.py               # Settings (link prediction toggles, thresholds)
├── pipeline.py             # Master orchestrator (KnowledgeGraphPipeline)
├── models/
│   └── schemas.py          # Pydantic models (GraphNode, GraphEdge, KnowledgeGraph)
├── storage/
│   └── database.py         # PostgreSQL persistence + link prediction via pgvector
├── api/
│   └── routes.py           # FastAPI endpoints
└── exporters/
    ├── neo4j_exporter.py   # Neo4j database export
    └── networkx_exporter.py # NetworkX graph export
```

## Integration

**Flow**: Agent 1 (Extraction) → Agent 2 (Resolution) → Agent 3 (Graph Builder Pro)

```python
# Agent 2 produces resolved clusters with centroid embeddings
from agent2_resolution.pipeline import EntityResolutionPipeline

agent2 = EntityResolutionPipeline()
resolution = agent2.process([payload])

# Agent 3 builds knowledge graph (optionally with link prediction)
from agent3_graph.pipeline import KnowledgeGraphPipeline

agent3 = KnowledgeGraphPipeline()

# Without predictions (default)
graph = agent3.build_graph(resolution.run_id)

# With link prediction enabled
graph = agent3.build_graph(resolution.run_id, include_predictions=True)

print(f"Graph: {graph.node_count} nodes, {graph.edge_count} edges")
```

## Link Prediction (Agent 4 Merged)

When `include_predictions=True`, Agent 3 uses pgvector centroid embeddings from Agent 2 to predict missing relationships:

```
For each pair of clusters (A, B):
  1. Get centroid embeddings from pgvector
  2. Calculate cosine similarity
  3. If similarity > LINK_PREDICTION_THRESHOLD AND no existing edge:
     → Add predicted edge with confidence = similarity
```

**Config:**
```python
INCLUDE_PREDICTIONS: bool = False         # Default off
LINK_PREDICTION_THRESHOLD: float = 0.85  # Min similarity for prediction
PREDICTION_MIN_CONFIDENCE: float = 0.70  # Min confidence to keep prediction
```

## Configuration

Update `.env`:

```env
# Database (shared with Agent 1 & 2)
DATABASE_URL=postgresql://ezekiel:08062006@localhost:5432/sih_evidence_db

# Neo4j (optional - for graph export)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Agent 3 specific (can override in .env)
INCLUDE_PREDICTIONS=true
LINK_PREDICTION_THRESHOLD=0.85
PREDICTION_MIN_CONFIDENCE=0.70
```

## Running Agent 3

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- `neo4j` — Neo4j database driver
- `networkx` — Graph operations
- `pgvector` — Vector similarity (requires PostgreSQL pgvector extension)

### 2. Start Agent 3 Server

```bash
python main_agent3.py
```

### 3. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/graph/build` | POST | Build knowledge graph |
| `/api/v1/graph/auto-build` | POST | Auto-trigger from pipeline |
| `/api/v1/graph/export/neo4j` | GET | Export to Neo4j |
| `/api/v1/graph/export/{format}` | GET | Export to JSON/NetworkX/GraphML |
| `/api/v1/graph/stats` | GET | Get graph statistics |
| `/api/v1/graph/query/neighbors` | GET | Query node neighbors |
| `/api/v1/graph/status` | GET | Health check |

### 4. Example API Calls

**Build graph with predictions:**
```bash
curl -X POST http://localhost:8002/api/v1/graph/build \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "RES-ABC12345",
    "include_predictions": true,
    "export_formats": ["json", "neo4j"]
  }'
```

**Export to Neo4j:**
```bash
curl "http://localhost:8002/api/v1/graph/export/neo4j?run_id=RES-ABC12345&include_predictions=true"
```

**Get statistics:**
```bash
curl "http://localhost:8002/api/v1/graph/stats?run_id=RES-ABC12345&include_networkx=true"
```

## Database Schema

Agent 3 uses tables from Agent 1 & 2, plus:

```sql
-- Knowledge graph metadata storage
CREATE TABLE knowledge_graphs (
    id SERIAL PRIMARY KEY,
    graph_id VARCHAR(128) UNIQUE NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    graph_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Output Structure

**KnowledgeGraph:**

```json
{
  "graph_id": "GRAPH-A1B2C3D4",
  "run_id": "RES-ABC12345",
  "nodes": [
    {
      "node_id": "CLU-00001",
      "canonical_name": "Rajesh Sharma",
      "entity_type": "PERSON",
      "source_entities": [1, 2, 3],
      "evidence_sources": ["EV-001", "EV-002"],
      "confidence": 0.97
    }
  ],
  "edges": [
    {
      "edge_id": "EDGE-ABC1-0001",
      "source_node": "CLU-00001",
      "target_node": "CLU-00002",
      "predicate": "works_for",
      "original_triples": [42],
      "confidence": 0.95,
      "temporal": "2024-01",
      "spatial": {"latitude": 19.0760, "longitude": 72.8777},
      "is_predicted": false
    },
    {
      "edge_id": "PRED-ABC1-0001",
      "source_node": "CLU-00001",
      "target_node": "CLU-00003",
      "predicate": "predicted_link",
      "confidence": 0.89,
      "is_predicted": true
    }
  ],
  "node_count": 15,
  "edge_count": 22,
  "created_at": "2024-01-15T10:30:00"
}
```

## Neo4j Integration

Predicted edges are marked with `is_predicted=true`:

```cypher
-- Get only real edges
MATCH (s)-[r:RELATION]->(t)
WHERE r.is_predicted = false
RETURN s, r, t

-- Get only predicted edges
MATCH (s)-[r:RELATION]->(t)
WHERE r.is_predicted = true
RETURN s, r, t

-- Get graph statistics
MATCH (s)-[r:RELATION]->(t)
RETURN count(s) as nodes, count(r) as edges,
       count(CASE WHEN r.is_predicted = true THEN 1 END) as predicted
```

## Next Steps

- **Agent 6 (GraphRAG)**: Query the knowledge graph with natural language
- **Visualization**: Web UI for interactive graph exploration
- **Validation**: UI for confirming/rejecting predicted links