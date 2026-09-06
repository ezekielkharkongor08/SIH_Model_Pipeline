# Agent 4 - GraphRAG Query Engine

## Overview

Agent 4 is the **GraphRAG Query Engine** that provides a natural language interface to the knowledge graph built by Agents 1, 2, and 3. It enables users to ask questions about the extracted entities, resolved clusters, and graph relationships in plain English.

**Key Features:**
- Natural language queries to Neo4j knowledge graph
- Automatic entity extraction from questions
- Path finding and relationship discovery
- Query result caching for performance
- Support for predicted edges (from Agent 3 link prediction)
- Confidence scoring for answers

## Architecture

```
agent4_graphRAG/
├── config.py               # Settings (LLM, thresholds, caching)
├── models/
│   └── schemas.py          # Pydantic models (Query, Result, Stats)
├── storage/
│   └── database.py         # Neo4j queries + context retrieval
├── api/
│   └── routes.py           # FastAPI endpoints
└── __init__.py             # Package initialization
```

## Integration

**Complete Flow**: Agent 1 (Extraction) → Agent 2 (Resolution) → Agent 3 (Graph) → Agent 4 (Query)

```python
from agent4_graphRAG.storage.database import GraphRAGRepository
from agent4_graphRAG.models.schemas import GraphRAGQuery

# Initialize the repository
repo = GraphRAGRepository()

# Create a query
query = GraphRAGQuery(
    query="Who works at TechCorp?",
    include_predictions=False,
    max_results=5
)

# Execute the query
result = repo.query_graph(query)

print(f"Answer: {result.answer}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Related nodes: {len(result.related_nodes)}")
print(f"Paths found: {len(result.related_paths)}")
```

## Query Types Supported

| Query Type | Example |
|-----------|---------|
| **Entity Lookup** | "Who is Rajesh Sharma?" |
| **Relationship Queries** | "Who works at TechCorp?" |
| **Path Finding** | "How is Rajesh connected to Priya?" |
| **Aggregation** | "How many people work at TechCorp?" |
| **Filtering** | "Show all persons in Mumbai" |

## Configuration

Update `.env` or `agent4_graphRAG/config.py`:

```env
# Database (shared with all agents)
DATABASE_URL=postgresql://ezekiel:08062006@localhost:5432/sih_evidence_db

# Neo4j (where knowledge graph is stored)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM for processing queries (local Ollama)
NL_LLM_PROVIDER=ollama
NL_LLM_BASE_URL=http://localhost:11434/v1
NL_LLM_MODEL_NAME=llama3.1:8b
NL_LLM_TEMPERATURE=0.1
NL_LLM_MAX_TOKENS=1024

# GraphRAG settings
MAX_CONTEXT_LENGTH=2000
MAX_PATH_LENGTH=3
SIMILARITY_THRESHOLD=0.7
TOP_K_RESULTS=5
ENABLE_QUERY_CACHE=true
QUERY_CACHE_TTL=3600
```

## Running Agent 4

### Option 1: Standalone Server (port 8003)

```bash
python main_agent4.py
```

Then access:
- Swagger UI: http://localhost:8003/docs
- API: http://localhost:8003/api/v1/graphrag/query

### Option 2: Unified Server (port 8000)

```bash
python main.py
```

All agents run on the same server:
- Agent 1 (Extraction): http://localhost:8000/api/v1/extraction/docs
- Agent 2 (Resolution): http://localhost:8000/api/v1/resolution/docs
- Agent 3 (Graph): http://localhost:8000/api/v1/graph/docs
- Agent 4 (GraphRAG): http://localhost:8000/api/v1/graphrag/docs

### Option 3: Run Demo

```bash
python demo_agent4_graphrag.py
```

## API Endpoints

### POST /api/v1/graphrag/query

Execute a natural language query against the knowledge graph.

**Request:**
```json
{
  "query": "Who works at TechCorp?",
  "run_id": "RES-ABC12345",
  "include_predictions": false,
  "max_results": 10
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "answer": "Based on the knowledge graph, the following people work at TechCorp: Rajesh Sharma, Priya Malhotra...",
    "confidence": 0.85,
    "supporting_evidence": ["EV-001", "EV-002"],
    "related_nodes": [
      {
        "node_id": "CLU-00001",
        "canonical_name": "Rajesh Sharma",
        "entity_type": "PERSON",
        "confidence": 0.97
      }
    ],
    "related_paths": [
      {
        "nodes": [...],
        "relationships": [...]
      }
    ],
    "query_time_ms": 45.23
  },
  "from_cache": false
}
```

### GET /api/v1/graphrag/query?q=your+question

Same as POST but via URL parameters (simpler for testing).

```bash
curl "http://localhost:8003/api/v1/graphrag/query?q=Who+works+at+TechCorp?"
```

### GET /api/v1/graphrag/examples

Get example queries that can be used.

### GET /api/v1/graphrag/stats

Get system statistics (total queries, cache hits, average time).

### POST /api/v1/graphrag/clear-cache

Clear the query cache.

### GET /api/v1/graphrag/status

Health check endpoint.

## How It Works

### Step 1: Query Input
```
"Who works at TechCorp?"
```

### Step 2: Entity Extraction
Extract potential entity names from the query:
```
["TechCorp", "works"]
```

### Step 3: Node Matching
Search Neo4j for nodes matching the extracted terms:
```
MATCH (n:Entity)
WHERE toLower(n.canonical_name) CONTAINS "techcorp"
RETURN n
```

### Step 4: Relationship Discovery
Find edges connecting the matching nodes:
```
MATCH (s:Entity)-[r:RELATION]->(t:Entity)
WHERE s IN matching_nodes OR t IN matching_nodes
RETURN s, r, t
```

### Step 5: Path Finding
Find shortest paths between matching nodes:
```
MATCH path = shortestPath((n)-[r:RELATION*]-(m))
WHERE length(path) <= 3
RETURN path
```

### Step 6: Answer Generation
Generate natural language answer from the retrieved context (template-based in this version):

```
"The entity 'TechCorp' is an ORGANIZATION with confidence 0.98.
It is associated with 3 source entities and appears in 2 evidence sources.
Key connections found:
1. TechCorp -> [employs] -> Rajesh Sharma -> [collaborates_with] -> Priya Malhotra"
```

## Caching

Query results are cached in memory to improve performance:

- **Cache Key**: MD5 hash of (query_text + run_id + include_predictions + max_results)
- **TTL**: Configurable via `QUERY_CACHE_TTL` (default 3600 seconds)
- **Enable/Disable**: Via `ENABLE_QUERY_CACHE` config

**Benefits:**
- Repeated queries answered instantly
- Reduced database load
- Faster response times

**Monitoring:**
```bash
curl http://localhost:8003/api/v1/graphrag/stats
```

Returns:
```json
{
  "total_queries": 42,
  "avg_query_time_ms": 125.5,
  "cache_hits": 15,
  "cache_misses": 27
}
```

## Performance Tuning

| Setting | Impact | Recommendation |
|---------|--------|-----------------|
| `MAX_PATH_LENGTH` | Query depth | 2-3 for fast queries, 4-5 for comprehensive |
| `TOP_K_RESULTS` | Result size | 5-10 for focused results, 20+ for exploration |
| `SIMILARITY_THRESHOLD` | Match sensitivity | 0.7 strict, 0.5 loose |
| `ENABLE_QUERY_CACHE` | Response speed | Enable in production |
| `QUERY_CACHE_TTL` | Freshness | 300s for real-time, 3600s for stability |

## Future Enhancements

1. **LLM Integration**: Use Ollama/local LLM for better answer generation
2. **Entity Linking**: More sophisticated entity extraction from queries
3. **Semantic Search**: Embed queries and find similar past queries
4. **Multi-hop Reasoning**: Better handling of complex multi-step questions
5. **Feedback Loop**: Learn from user corrections to improve answers
6. **Visualization**: Return graph structures for client-side visualization