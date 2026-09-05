# SIH Knowledge Graph Extraction & Resolution System

A complete end-to-end system for forensic evidence extraction, entity resolution, and knowledge graph building.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      UNIFIED FASTAPI SERVER (Port 8000)              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Agent 1: Extraction Engine (/api/v1/extraction)             │   │
│  │ • Extract entities & triples from JSON, TXT, Images         │   │
│  │ • Normalize geo/temporal data                               │   │
│  │ • Store in PostgreSQL (evidence_records, extracted_*)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                            ↓ (ExtractionPayload)                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Agent 2: Entity Resolution (/api/v1/resolution)             │   │
│  │ • BGE-m3 embeddings + Metaphone blocking + HAC clustering    │   │
│  │ • Resolve entities across documents                          │   │
│  │ • Build resolved triples (graph edges)                       │   │
│  │ • Track cluster-to-entity & cluster-to-evidence mappings    │   │
│  │ • Store in PostgreSQL (entity_clusters, resolved_triples)    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                            ↓ (ResolutionPayload + Run ID)            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Agent 3: Knowledge Graph Builder (/api/v1/graph)             │   │
│  │ • Build connected knowledge graph from Agent 1 & 2 data       │   │
│  │ • Export to Neo4j (PRIMARY), NetworkX, JSON, GraphML          │   │
│  │ • Graph analysis: statistics, shortest paths, neighbors       │   │
│  │ • Store metadata in PostgreSQL (knowledge_graphs)             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
          ┌────────────────────┼────────────────────┐
          ↓                    ↓                    ↓
     PostgreSQL           Neo4j Graph DB         NetworkX
   (Metadata)            (Graph Queries)      (Local Analysis)
```

## Database Schema

### Agent 1 Tables (Evidence & Extraction)
- `evidence_records` - Raw evidence content (JSON/TXT/IMAGE)
- `extracted_entities` - Extracted entities with confidence scores
- `extracted_triples` - Subject-Predicate-Object relationships

### Agent 2 Tables (Entity Resolution & Graph)
- `entity_clusters` - Resolved canonical entities
- `resolution_decisions` - Pending review pairs (0.80-0.94 similarity)
- `cluster_entity_membership` - Maps clusters to source entities
- `resolved_triples` - Connected clusters through predicates
- `cluster_evidence_sources` - Evidence traceability per cluster

### Agent 3 Tables (Knowledge Graph Metadata)
- `knowledge_graphs` - Graph build metadata and full JSONB structure

## API Endpoints

### Agent 1: Extraction
```bash
POST /api/v1/extraction/extract
  Upload file (JSON/TXT/Image) → Extract entities & triples

GET /api/v1/extraction/status
  Health check & supported formats
```

### Agent 2: Entity Resolution
```bash
POST /api/v1/resolution/resolve
  [ExtractionPayload] → Resolve entities across documents
  
POST /api/v1/resolution/resolve-mentions
  [EntityMention] → Direct mention-based resolution

GET /api/v1/resolution/status
  Health check & resolution thresholds (0.95/0.80)
```

### Agent 3: Knowledge Graph Builder
```bash
# Building & Exporting
POST /api/v1/graph/build
  {run_id, export_formats: ["json", "neo4j", "networkx"]}
  → Build graph from Agent 2 resolution run

POST /api/v1/graph/auto-build
  Auto-trigger endpoint for pipeline integration (future)

GET /api/v1/graph/export/neo4j?run_id=RES-XXXXX
  → Build and export directly to Neo4j

GET /api/v1/graph/export/{format}?run_id=RES-XXXXX
  format: json, networkx, graphml

# Analysis & Queries
GET /api/v1/graph/stats?run_id=RES-XXXXX&include_networkx=true
  → Graph statistics (nodes, edges, centrality measures)

GET /api/v1/graph/query/neighbors?run_id=RES-XXXXX&node_id=CLU-00001&depth=1
  → Find neighbors up to specified depth

GET /api/v1/graph/status
  → Health check & capabilities
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL
```bash
# Apply all schemas
psql -h localhost -U postgres -d sih_evidence_db -f schema.sql
psql -h localhost -U postgres -d sih_evidence_db -f schema_agent2.sql
psql -h localhost -U postgres -d sih_evidence_db -f schema_agent3.sql
```

### 3. Start Unified Server
```bash
python main.py
# Server runs on http://localhost:8000
```

### 4. Try Agent 1: Extract Evidence
```bash
curl -X POST http://localhost:8000/api/v1/extraction/extract \
  -F "file=@sample.json"
  
# Response: ExtractionPayload with evidence_id
# {
#   "evidence_id": "EV-sample-1704067200000-a1b2c3",
#   "entities": [...],
#   "triples": [...]
# }
```

### 5. Try Agent 2: Resolve Entities
```bash
curl -X POST http://localhost:8000/api/v1/resolution/resolve \
  -H "Content-Type: application/json" \
  -d '[{extraction_payload_from_step_4}]'
  
# Response: ResolutionPayload with run_id
# {
#   "run_id": "RES-A1B2C3D4",
#   "clusters": [...],
#   "resolved_triples": [...],
#   "evidence_sources": [...]
# }
```

### 6. Try Agent 3: Build Knowledge Graph
```bash
curl -X POST http://localhost:8000/api/v1/graph/build \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "RES-A1B2C3D4",
    "export_formats": ["json", "neo4j"]
  }'
  
# Response: Graph metadata and exports
# {
#   "success": true,
#   "graph_id": "GRAPH-A1B2C3D4",
#   "statistics": {
#     "node_count": 25,
#     "edge_count": 48
#   }
# }
```

## Key Features

### Agent 1: Universal Extraction
- **Multi-format support**: JSON, TXT, PNG, JPG, JPEG, TIFF
- **Entity extraction**: 12 entity types (PERSON, ORGANIZATION, LOCATION, etc.)
- **Relationship extraction**: Subject-Predicate-Object triples
- **Normalization**: Temporal (via SUTime) and Geospatial (via GeoPy)
- **Confidence scoring**: Per-entity and per-triple confidence

### Agent 2: Entity Resolution
- **BGE-m3 embeddings**: Fast, accurate multilingual entity embeddings
- **Metaphone blocking**: Efficient candidate pair generation
- **Hierarchical Agglomerative Clustering**: Similarity-based entity merging
- **Threshold-based decisions**:
  - ≥ 0.95: MERGED (same entity)
  - 0.80-0.94: PENDING_REVIEW (human/LLM decision needed)
  - < 0.80: REJECTED (distinct entities)
- **Cross-document resolution**: Resolves duplicates within and across documents
- **Relational tracking**: Maintains entity-to-cluster and cluster-to-evidence links

### Agent 3: Knowledge Graph Building
- **Neo4j export** (PRIMARY): Property graph database with Cypher querying
- **NetworkX export**: Python graph library for analysis
- **JSON/GraphML export**: Standard formats for portability
- **Graph analysis**:
  - Centrality measures (degree, betweenness, PageRank)
  - Component detection
  - Shortest path queries
  - Neighbor discovery
- **Full traceability**: Track which evidence documents contributed to each node/edge

## Data Flow Example

```
Raw Evidence File (evidence.json)
         ↓
    Agent 1: Extract
    ├─ entities: [John (PERSON, conf=0.98), ACME Corp (ORG, conf=0.95)]
    └─ triples: [(John works_for ACME Corp)]
         ↓
    Evidence stored in PostgreSQL
         ↓
    Agent 2: Resolve (batch multiple evidences)
    ├─ Embed: BGE-m3
    ├─ Block: Metaphone
    ├─ Cluster: HAC
    └─ Output:
       ├─ Clusters: [CLU-00001: John Smith, CLU-00002: ACME Corporation]
       ├─ Triples: [CLU-00001 --works_for--> CLU-00002]
       └─ Mappings: John/PERSON/evidence1 → CLU-00001
         ↓
    Resolution run stored in PostgreSQL
         ↓
    Agent 3: Build Knowledge Graph
    ├─ Query PostgreSQL for all resolved entities & relationships
    ├─ Build graph nodes & edges
    └─ Export to:
       ├─ Neo4j (Cypher queries: MATCH (p:Entity)-[r:RELATION]->(org))
       ├─ NetworkX (Python analysis)
       └─ JSON (REST APIs, visualization)
```

## Configuration

### Environment Variables (.env)
```
# Database (shared across all agents)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sih_evidence_db

# LLM (Agent 1)
LLM_PROVIDER=vllm
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL_NAME=meta-llama/Meta-Llama-3-8B-Instruct

# Neo4j (Agent 3)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Graph building
AUTO_TRIGGER_GRAPH_BUILD=false  # Set to true for automatic pipeline
```

## Query Examples

### SQL: Trace a cluster back to source evidence
```sql
SELECT 
    ec.canonical_name,
    ec.entity_type,
    ces.evidence_id,
    er.input_format,
    er.created_at
FROM entity_clusters ec
JOIN cluster_evidence_sources ces ON ec.cluster_id = ces.cluster_id
JOIN evidence_records er ON ces.evidence_id = er.evidence_id
WHERE ec.cluster_id = 'CLU-00001';
```

### SQL: Find all relationships from a cluster
```sql
SELECT 
    ec1.canonical_name as source,
    rt.predicate,
    ec2.canonical_name as target,
    rt.confidence
FROM entity_clusters ec1
JOIN resolved_triples rt ON ec1.cluster_id = rt.subject_cluster_id
JOIN entity_clusters ec2 ON rt.object_cluster_id = ec2.cluster_id
WHERE ec1.canonical_name LIKE '%John%';
```

### Cypher (Neo4j): Graph traversal
```cypher
MATCH (p:Entity {entity_type: 'PERSON'})-[r:RELATION]->(org:Entity {entity_type: 'ORGANIZATION'})
WHERE p.graph_id = 'GRAPH-A1B2C3D4'
RETURN p.canonical_name as person, r.predicate as relationship, org.canonical_name as organization;
```

### Python (NetworkX): Graph analysis
```python
import networkx as nx
from agent3_graph.exporters.networkx_exporter import NetworkxExporter

# Build and export graph
from agent3_graph.pipeline import KnowledgeGraphPipeline
pipeline = KnowledgeGraphPipeline()
graph = pipeline.build_graph('RES-A1B2C3D4')
nx_graph = pipeline.export_to_networkx(graph)

# Analyze
exporter = NetworkxExporter()
stats = exporter.compute_statistics(nx_graph)
print(f"Density: {stats['basic']['density']}")
print(f"PageRank top nodes: {stats['centrality']['top_pagerank']}")

# Find neighbors
neighbors = exporter.get_neighbors(nx_graph, 'CLU-00001', depth=2)
print(f"Neighbors: {neighbors}")
```

## Testing

```bash
# Run test suite
pytest tests/

# Test Agent 1 extraction
pytest tests/test_agent1_extraction.py

# Test Agent 2 resolution
pytest tests/test_agent2_resolution.py

# Test Agent 3 graph building
pytest tests/test_agent3_graph.py
```

## Performance Considerations

- **Entity Resolution**: O(n log n) with BGE-m3 + HAC
- **Graph Building**: O(n + m) where n=clusters, m=triples
- **Neo4j Queries**: Index on graph_id, node_id, predicate for fast retrieval
- **Memory**: NetworkX holds full graph in memory (suitable for <100k nodes)

## Future Enhancements

1. **Auto-trigger pipeline**: Agent 2 automatically triggers Agent 3 graph build
2. **Graph visualization**: Web UI for interactive graph exploration
3. **Advanced queries**: SPARQL endpoint for semantic queries
4. **Incremental updates**: Update graphs without full rebuild
5. **Machine learning**: Use graph embeddings for entity classification
6. **Distributed processing**: Parallelize across document batches

## Troubleshooting

### PostgreSQL connection failed
```
Check DATABASE_URL in .env
Verify PostgreSQL is running: psql -h localhost -U postgres -l
```

### Neo4j export failed
```
Check NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env
Verify Neo4j is running: curl http://localhost:7687
```

### Missing tables
```
Re-apply schemas:
psql -h localhost -U postgres -d sih_evidence_db -f schema.sql
psql -h localhost -U postgres -d sih_evidence_db -f schema_agent2.sql
psql -h localhost -U postgres -d sih_evidence_db -f schema_agent3.sql
```

## References

- **BGE-m3**: BAAI/bge-m3 embeddings (https://huggingface.co/BAAI/bge-m3)
- **Neo4j**: Graph database & Cypher query language (https://neo4j.com/)
- **NetworkX**: Python network analysis (https://networkx.org/)
- **Metaphone**: Phonetic algorithm for blocking (https://en.wikipedia.org/wiki/Metaphone)

## License

Internal project for SIH (Smart India Hackathon)