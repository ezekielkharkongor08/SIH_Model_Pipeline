# SIH Pipeline Execution Guide

## Complete 4-Agent Forensic Evidence Processing Pipeline

This guide explains how to execute the complete pipeline on the FIR dataset and verify results.

## 🚀 Quick Start

### Option 1: Unified Server (All Agents)
```bash
# Start all agents on port 8000
python main.py

# Access individual agent docs:
# Agent 1: http://localhost:8000/api/v1/extraction/docs
# Agent 2: http://localhost:8000/api/v1/resolution/docs
# Agent 3: http://localhost:8000/api/v1/graph/docs
# Agent 4: http://localhost:8000/api/v1/graphrag/docs
```

### Option 2: Individual Agent Servers
```bash
# Agent 1 only (port 8000)
python main.py

# Agent 2 only (port 8001) 
python -c "
import uvicorn
from agent2_resolution.api.routes import router as resolution_router
from fastapi import FastAPI
app = FastAPI()
app.include_router(resolution_router, prefix='/api/v1/resolution')
uvicorn.run(app, host='127.0.0.1', port=8001)
"

# Agent 3 only (port 8002)
python -c "
import uvicorn
from agent3_graph.api.routes import router as graph_router
from fastapi import FastAPI
app = FastAPI()
app.include_router(graph_router, prefix='/api/v1/graph')
uvicorn.run(app, host='127.0.0.1', port=8002)
"

# Agent 4 only (port 8003)
python main_agent4.py
```

## 📊 Test Execution Steps

### 1. Prepare Environment
```bash
# Activate virtual environment
source .venv/Scripts/activate

# Verify dependencies
pip list | grep -E "(fastapi|uvicorn|sqlalchemy|neo4j|ollama|loguru)"

# Check services
# PostgreSQL: should be running on localhost:5432
# Neo4j: should be running on localhost:7687 (bolt protocol)
# Ollama: should be running with llama3.1:8b model
```

### 2. Run Complete Pipeline Test
```bash
# Execute the test script (processes FIR images)
python run_pipeline_test.py

# Monitor progress in:
# - Console output
# - test_results/logs/pipeline_test.log
```

### 3. Verify Results
```bash
# Check final report
cat test_results/final_report.json

# Check individual agent results
cat test_results/agent1_extraction/summary.json
cat test_results/agent2_resolution/summary.json  
cat test_results/agent3_graph/summary.json
cat test_results/agent4_graphrag/summary.json
```

## 🔧 Configuration

### Environment Variables (.env file)
```env
# Database (PostgreSQL)
DATABASE_URL=postgresql://ezekiel:08062006@localhost:5432/sih_evidence_db

# Neo4j (for Agent 3)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password_here

# LLM (Ollama for Agents 1 & 4)
NL_LLM_PROVIDER=ollama
NL_LLM_BASE_URL=http://localhost:11434/v1
NL_LLM_MODEL_NAME=llama3.1:8b
NL_LLM_TEMPERATURE=0.1
NL_LLM_MAX_TOKENS=1024

# Agent 2 Settings
HAC_LINKAGE=complete
MERGED_THRESHOLD=0.95
PENDING_THRESHOLD_MIN=0.80
PENDING_THRESHOLD_MAX=0.95
METAPHONE_MAX_KEY_LENGTH=4
REUSE_THRESHOLD=0.90

# Agent 3 Settings
INCLUDE_PREDICTIONS=false
LINK_PREDICTION_THRESHOLD=0.85
PREDICTION_MIN_CONFIDENCE=0.70

# Agent 4 Settings
MAX_CONTEXT_LENGTH=2000
MAX_PATH_LENGTH=3
SIMILARITY_THRESHOLD=0.7
TOP_K_RESULTS=5
ENABLE_QUERY_CACHE=true
QUERY_CACHE_TTL=3600
```

## 📁 Output Directory Structure

After successful execution:
```
test_results/
├── agent1_extraction/
│   ├── extraction_results.json    # Per-FIR extraction details
│   └── summary.json              # Entity/triple counts
├── agent2_resolution/
│   ├── resolution_results.json    # Clusters + pending review
│   └── summary.json              # Deduplication metrics
├── agent3_graph/
│   ├── graph_results.json        # Graph statistics
│   └── summary.json              # Node/edge counts
├── agent4_graphrag/
│   ├── query_results.json        # Test query responses
│   └── summary.json              # Query performance & cache stats
├── logs/
│   └── pipeline_test.log         # Detailed execution timeline
└── final_report.json             # Consolidated test report
```

## 🔍 Verifying Deduplication Worked

### Key Metrics to Check:
1. **Agent 2 Summary**: 
   - `deduplication_ratio_percent` > 0% indicates successful deduplication
   - Formula: `(1 - clusters/mentions) × 100`
   - Example: 200 mentions → 80 clusters = 60% deduplication

2. **Pending Review Pairs**:
   - Shows uncertain matches (0.80-0.95 similarity) needing manual validation
   - Empty array = all matches were clear-cut (≥0.95 or <0.80)

3. **Graph Verification**:
   - Agent 3 node count should match Agent 2 cluster count
   - Agent 3 edge count should match Agent 2 resolved triples count

4. **Sample Validation**:
   - Check that duplicate names across FIRs appear as single clusters
   - Verify centroid embeddings stored in entity_clusters table

## 📈 Example Successful Output

After processing 20 FIR images with repeated names:
```
AGENT 1 RESULTS:
- Entities extracted: 320
- Triples extracted: 145
- Evidence documents: 20

AGENT 2 RESULTS:  
- Total mentions: 320
- Total clusters: 128 (60% deduplication)
- Pending review: 15 pairs
- Resolved triples: 98

AGENT 3 RESULTS:
- Graph nodes: 128 (matches clusters)
- Graph edges: 98 (matches triples)
- Neo4j export: SUCCESS

AGENT 4 RESULTS:
- Queries successful: 5/5
- Avg response time: 1.2s
- Cache hit rate: 40%
```

## 🛠️ Troubleshooting

### Common Issues & Fixes:

1. **LLM Connection Failed**
   - Symptom: `LLM extraction failed: connection errors`
   - Fix: Start Ollama: `ollama serve` in separate terminal
   - Verify model: `ollama run llama3.1:8b`

2. **Database Connection Failed**  
   - Symptom: `Failed to persist extraction payload`
   - Fix: Check PostgreSQL: `sudo service postgresql status`
   - Verify .env DATABASE_URL format

3. **Neo4j Connection Failed**
   - Symptom: `Agent 3: Neo4j connection failed`  
   - Fix: Start Neo4j: `neo4j start`
   - Check bolt://localhost:7687 accessibility

4. **Processing Timeout**
   - Symptom: Test exits before completing all images
   - Fix: Increase timeout or process in batches:
     ```bash
     # Process first 10 images
     sed -i 's/\[:20\]/\[:10\]/' run_pipeline_test.py
     python run_pipeline_test.py
     # Process remaining 10
     sed -i 's/\[:10\]/\[10:20\]/' run_pipeline_test.py
     python run_pipeline_test.py
     ```

5. **Missing Dependencies**
   - Symptom: `ModuleNotFoundError: No module named 'X'`
   - Fix: `pip install -r requirements.txt`

## 📝 API Endpoints for Manual Testing

Once servers are running:

### Agent 1 - Extraction
```bash
curl -X POST "http://localhost:8000/api/v1/extract" \
  -F "file=@fir_dataset/FIR_specimen_01_211-2024.png"
```

### Agent 2 - Resolution  
```bash
curl -X POST "http://localhost:8000/api/v1/resolution/resolve" \
  -H "Content-Type: application/json" \
  -d '{"run_id": "TEST-RUN"}'
```

### Agent 3 - Graph
```bash
curl -X POST "http://localhost:8000/api/v1/graph/auto-build" \
  -H "Content-Type: application/json" \
  -d '{"run_id": "TEST-RUN", "include_predictions": false}'
```

### Agent 4 - GraphRAG
```bash
curl -X POST "http://localhost:8000/api/v1/graphrag/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the main suspects?", "max_results": 5}'
```

## ✅ Success Criteria

The pipeline is working correctly when:
1. **All 4 agents start without errors**
2. **Data flows**: Extraction → Resolution → Graph → Query
3. **Deduplication occurs**: Cluster count < Entity count  
4. **Graph is built**: Nodes and edges created in Neo4j
5. **Queries return results**: Natural language questions answered
6. **Output files generated**: All test_results/* directories populated

## 📚 Related Files

- `DUPLICATE_HANDLING_SUMMARY.md` - Detailed deduplication analysis
- `AGENT4_README.md` - Complete GraphRAG documentation  
- `run_pipeline_test.py` - Automated test script
- Individual agent directories contain specific documentation

## 🔄 Making Tests Reproducible

To reset and run again:
```bash
# Clear test results
rm -rf test_results/*

# Optional: Clear database (careful in production!)
# python -c "from sqlalchemy import create_engine; from agent1_extraction.config import settings; e=create_engine(settings.DATABASE_URL); e.execute('TRUNCATE TABLE extracted_entities, extracted_triples, entity_clusters, resolution_decisions, resolved_triples RESTART IDENTITY CASCADE')"

# Re-run test
python run_pipeline_test.py
```

---
**Pipeline Ready**: Execute `python run_pipeline_test.py` to begin testing the complete forensic evidence processing workflow with intelligent deduplication.