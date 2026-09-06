# Agent 2 - Entity Resolution System

## 📋 Overview

Agent 2 is the **Entity Resolution Engine** that takes entity mentions extracted by Agent 1 and resolves them into unified clusters using:

- **BGE-m3 embeddings** for semantic similarity
- **Metaphone blocking** for efficient candidate pair generation
- **Hierarchical Agglomerative Clustering (HAC)** for grouping
- **0.95/0.80 threshold matrix** for merge/pending/reject decisions

## 🏗️ Architecture

```
agent2_resolution/
├── models/
│   └── schemas.py          # Pydantic models (EntityMention, EntityCluster, ResolutionPayload)
├── embeddings/
│   └── embedder.py         # BGE-m3 embedding layer (sentence-transformers)
├── blocking/
│   └── blocker.py          # Metaphone phonetic blocking to reduce O(n²) comparisons
├── clustering/
│   └── clusterer.py        # HAC with threshold matrix (merge/pending/reject)
├── storage/
│   └── database.py         # PostgreSQL persistence (entity_clusters, resolution_decisions)
├── api/
│   └── routes.py           # FastAPI endpoints (/resolve, /resolve-mentions)
├── config.py               # Settings (thresholds, model config, DB URL)
└── pipeline.py             # Master orchestrator (EntityResolutionPipeline)
```

## 🔗 Integration with Agent 1

**Flow**: Agent 1 (Extraction) → Agent 2 (Resolution)

```python
# Agent 1 produces extraction payloads
from agent1_extraction.pipeline import UniversalExtractionPipeline

agent1 = UniversalExtractionPipeline()
payload = agent1.process(evidence_id="EV-001", raw_content=doc, filename="doc.txt")

# Agent 2 consumes them and resolves entities
from agent2_resolution.pipeline import EntityResolutionPipeline

agent2 = EntityResolutionPipeline()
resolution = agent2.process([payload])  # Pass list of Agent 1 payloads

print(f"Clusters: {len(resolution.clusters)}")
print(f"Pending Review: {len(resolution.pending_review)}")
```

## 🎯 Threshold Matrix (Contract Rule)

| Similarity Score | Decision | Action |
|------------------|----------|--------|
| **>= 0.95** | `MERGED` | Auto-merge into same entity cluster |
| **0.80 – 0.94** | `PENDING_REVIEW` | Route to human review (or auto-approve stub for demo) |
| **< 0.80** | `REJECTED` | Keep as distinct entities |

## 📂 File Responsibilities

### Core Files

| File | Responsibility |
|------|----------------|
| **pipeline.py** | Orchestrates entire resolution flow: collect mentions → group by type → embed → block → cluster → apply thresholds → persist |
| **embeddings/embedder.py** | Load BGE-m3 model, convert entity surface strings to unit-norm float32 vectors |
| **blocking/blocker.py** | Group entities by Metaphone code, return candidate pairs (avoids full O(n²)) |
| **clustering/clusterer.py** | Run scipy HAC, cut dendrogram at thresholds, build clusters + pending_review |
| **storage/database.py** | Persist clusters and pending pairs to Postgres (`entity_clusters`, `resolution_decisions` tables) |
| **api/routes.py** | FastAPI endpoints to expose resolution as REST API |
| **config.py** | Centralized settings (thresholds, model name, DB URL) |
| **models/schemas.py** | Pydantic data contracts (EntityMention, EntityCluster, ResolutionPayload, ResolutionPair) |

### Entry Points

| File | Purpose |
|------|---------|
| **main_agent2.py** | Standalone FastAPI server for Agent 2 (runs on port 8001) |
| **run_agent2_demo.py** | End-to-end demo: runs Agent 1 extraction, feeds output to Agent 2, prints clusters + pending pairs |

## 🚀 Running Agent 2

### 1. Install Dependencies

```bash
# Activate your virtual environment first
pip install -r requirements.txt
```

Key Agent 2 dependencies:
- `sentence-transformers>=2.2.0` — BGE-m3 embeddings
- `scipy>=1.11.0` — HAC clustering
- `jellyfish>=1.0.0` — Metaphone blocking

### 2. Configure Settings

Update `.env` or modify `agent2_resolution/config.py`:

```env
# Embedding model
EMBED_MODEL=BAAI/bge-m3
EMBED_DEVICE=cpu  # or "cuda" for GPU

# Threshold matrix
MERGE_THRESHOLD=0.95
REVIEW_THRESHOLD=0.80

# HAC linkage
HAC_LINKAGE=average  # options: average, complete, single

# Agent 1 base URL (for fetching payloads if needed)
AGENT1_BASE_URL=http://127.0.0.1:8000

# Shared database
DATABASE_URL=postgresql://ezekiel:08062006@localhost:5432/sih_evidence_db
```

### 3. Run the Demo

```bash
python run_agent2_demo.py
```

This will:
1. Run Agent 1 on 4 test documents (CDR, Chat, FIR JSON, FIR TXT)
2. Feed all extracted entities to Agent 2
3. Print resolved clusters and pending review pairs

### 4. Run as API Server

```bash
# Agent 1 server (port 8000)
python main.py

# Agent 2 server (port 8001)
python main_agent2.py
```

Then POST to Agent 2:

```bash
curl -X POST http://localhost:8001/api/v1/resolution/resolve \
  -H "Content-Type: application/json" \
  -d '[{...Agent 1 payloads...}]'
```

## 🗄️ Database Schema

Agent 2 creates two new tables:

```sql
-- Resolved entity clusters
CREATE TABLE entity_clusters (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    cluster_id VARCHAR(64) UNIQUE NOT NULL,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    avg_similarity FLOAT NOT NULL,
    member_count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Pending review pairs (0.80–0.94 band)
CREATE TABLE resolution_decisions (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    mention_a VARCHAR(255) NOT NULL,
    mention_b VARCHAR(255) NOT NULL,
    similarity FLOAT NOT NULL,
    decision VARCHAR(50) NOT NULL,  -- MERGED | PENDING_REVIEW | REJECTED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## 📊 Output Structure

**ResolutionPayload**:

```json
{
  "run_id": "RES-A3F2B891",
  "evidence_ids": ["EV-CDR-2024-002", "EV-CHAT-2024-003"],
  "clusters": [
    {
      "cluster_id": "CLU-00001",
      "canonical": "Rajesh Sharma",
      "entity_type": "PERSON",
      "members": [
        {"surface": "Rajesh Sharma", "evidence_id": "EV-FIR-2024-001"},
        {"surface": "R. Sharma", "evidence_id": "EV-CHAT-2024-003"}
      ],
      "avg_similarity": 0.97
    }
  ],
  "pending_review": [
    {
      "mention_a": "Vikram Malhotra",
      "mention_b": "V. Malhotra",
      "similarity": 0.89,
      "decision": "PENDING_REVIEW"
    }
  ],
  "total_mentions": 24,
  "total_clusters": 18,
  "execution_time_ms": 1250.43,
  "status": "SUCCESS"
}
```

## 🔧 Minimal Complexity Design

Agent 2 mirrors Agent 1's structure for consistency:

| Concept | Agent 1 | Agent 2 |
|---------|---------|---------|
| **Pydantic schemas** | `ExtractionPayload` | `ResolutionPayload` |
| **Main orchestrator** | `UniversalExtractionPipeline` | `EntityResolutionPipeline` |
| **Config** | `agent1_extraction/config.py` | `agent2_resolution/config.py` |
| **Storage** | `storage/database.py` | `storage/database.py` |
| **API** | `api/routes.py` | `api/routes.py` |
| **Entry point** | `main.py` (port 8000) | `main_agent2.py` (port 8001) |

## 🎓 For SIH Demo

1. **Run both agents**:
   ```bash
   python main.py          # Agent 1 on :8000
   python main_agent2.py   # Agent 2 on :8001
   ```

2. **Show end-to-end flow**:
   ```bash
   python run_agent2_demo.py
   ```

3. **Key demo points**:
   - Agent 1 extracts entities from multiple document types
   - Agent 2 resolves duplicate/variant mentions across documents
   - Threshold matrix auto-decides: merge (≥0.95), review (0.80–0.94), or reject (<0.80)
   - All results persist to PostgreSQL for graph analytics

## 📈 Next Steps

- **Human Review Interface**: Build UI for `pending_review` items
- **Feedback Loop**: Let reviewers confirm/reject, retrain threshold matrix
- **Knowledge Graph**: Use resolved clusters as nodes for relationship graph
- **Incremental Resolution**: Process new documents without re-clustering everything
