# SIH Agent Pipeline: Forensic Information Extraction & GraphRAG System

## 1. WHAT IS THE PROJECT?
The project is a multi-agent AI system designed for forensic information extraction from unstructured evidence (text, JSON, images). It processes evidence through four sequential agents to build a queryable knowledge graph that supports natural language questioning.

**Overall Pipeline:**
- **Input:** Raw evidence files (text, JSON, images)
- **Agent 1:** Extracts entities and subject-predicate-object triples
- **Agent 2:** Resolves entity mentions into clusters and builds resolved triples
- **Agent 3:** Constructs a knowledge graph from resolved entities and triples
- **Agent 4:** Enables natural language queries against the knowledge graph

**Core Technology:** The system uses BGE-m3 embeddings for entity resolution, Hierarchical Agglomerative Clustering (HAC) for entity grouping, Neo4j for graph storage, and LLMs for extraction and query synthesis.

## 2. AGENT PIPELINE

**Agent 1: Universal Forensic Extraction Engine**
- **Input:** Raw evidence (bytes) and filename
- **Processing:** 
  1. Parses input (JSON, text, or image via OCR)
  2. Applies regex extraction for predefined patterns (phones, emails, etc.)
  3. Uses LLM to extract subject-predicate-object triples with entity typing
  4. Verifies and aligns entity spans, normalizes locations
- **Output:** `ExtractionPayload` containing:
  - `evidence_id` (SHA-256 hash-based)
  - List of `ExtractedEntity` (with type, canonical name, span)
  - List of `ExtractedTriple` (subject, predicate, object, confidence)
  - Stored in PostgreSQL via SQLAlchemy ORM (tables: `evidence_records`, `extracted_entities`, `extracted_triples`)

**Agent 2: Entity Resolution Engine (BGE-m3 + HAC clustering)**
- **Input:** List of `ExtractionPayload` objects from Agent 1
- **Processing:**
  1. Extracts all entity mentions across payloads
  2. Groups mentions by entity type (PERSON, LOCATION, etc.)
  3. For each type:
     - Generates BGE-m3 embeddings (unit-norm float32 vectors, 1024-dim)
     - Applies Metaphone blocking to reduce comparison space
     - Runs Hierarchical Agglomerative Clustering (HAC) with cosine distance
     - Uses threshold matrix (0.95 for same-type, 0.80 for cross-type) to form clusters
  4. Maps resolved triples (subject-predicate-object) to cluster IDs
- **Output:** `ResolutionPayload` containing:
  - `run_id` (unique identifier)
  - List of resolved `Cluster` (each with ID, centroid embedding, member mentions)
  - List of `ResolvedTriple` (subject_cluster_id, predicate, object_cluster_id)
  - Evidence sources linking clusters to original evidence
  - Stored in PostgreSQL (tables: `resolution_runs`, `clusters`, `cluster_mentions`, `resolved_triples`)

**Agent 3: Knowledge Graph Builder (with link prediction)**
- **Input:** `run_id` from Agent 2 resolution
- **Processing:**
  1. Retrieves resolved entities and triples from Agent 2 database
  2. Constructs graph nodes (one per resolved cluster) with properties:
     - `node_id` (cluster ID), `canonical_name`, `entity_type`, `confidence`
  3. Constructs graph edges from resolved triples:
     - `predicate` as edge type, `confidence` as property
  4. Optionally predicts missing links using similarity-based heuristics
- **Output:** `KnowledgeGraph` object containing:
  - `graph_id`, `node_count`, `edge_count`
  - List of `GraphNode` and `GraphEdge` (with `is_predicted` flag)
  - Exported as JSON, Neo4j, or NetworkX format

**Agent 4: GraphRAG Query Engine (natural language interface)**
- **Input:** Natural language query string
- **Processing:**
  1. Extracts query terms and classifies intent (PERSON, LOCATION, etc.)
  2. Generates BGE-m3 embedding of the full query
  3. Uses pgvector (via Agent 2's resolution repository) to find similar clusters by cosine similarity
  4. Retrieves matching nodes and their 1-hop/shortest paths from Neo4j
  5. Generates natural language answer with supporting evidence using LLM synthesis
- **Output:** `GraphRAGResult` containing:
  - `answer` (natural language response)
  - `confidence` score (0.0-1.0)
  - List of `supporting_evidence` (evidence IDs)
  - List of `related_nodes` (matched entities with IDs)
  - List of `related_paths` (entity connections as paths)

**Data Flow Between Agents:**
```
Agent 1 Output (ExtractionPayload) 
    → Saved to PostgreSQL
Agent 2 Input (reads ExtractionPayload from PostgreSQL)
    → Agent 2 Output (ResolutionPayload) 
    → Saved to PostgreSQL
Agent 3 Input (run_id from ResolutionPayload)
    → Agent 3 Output (KnowledgeGraph) 
    → Exported to Neo4j (and optionally NetworkX/JSON)
Agent 4 Input (Natural language query)
    → Queries Neo4j for graph context 
    → Uses Agent 2's embeddings/pgvector for similarity search
    → Agent 4 Output (GraphRAGResult)
```

## 3. EMBEDDING CONVERSION
- **Model:** BGE-m3 (via `sentence-transformers`)
- **Input:** Entity surface strings (e.g., "Rajesh Sharma", "Mumbai")
- **Processing:** Text → tokenized → transformer → pooled embedding → L2-normalized to unit norm
- **Output:** Float32 vector of length 1024 (default BGE-m3 dimension)
- **Storage:** 
  - Agent 2: Cluster centroid embeddings stored in PostgreSQL (`clusters.centroid_embedding` as vector)
  - Agent 4: Query embeddings computed on-the-fly for similarity search against stored centroids
- **Note:** Uses `normalize_embeddings=True` in sentence-transformers for unit vectors

## 4. CLUSTERING / ENTITY RESOLUTION
- **Data:** Entity mention surface texts (grouped by entity type)
- **Similarity Method:** Cosine distance on BGE-m3 embeddings
- **Algorithm:** Hierarchical Agglomerative Clustering (HAC) with average linkage
- **Thresholds:** 
  - Same entity type: merge if similarity ≥ 0.95
  - Cross entity type: merge if similarity ≥ 0.80
- **Process:** 
  1. Start with each mention as own cluster
  2. Iteratively merge closest cluster pair until no pair meets threshold
  3. Assign globally unique cluster IDs (format: `CLU-#####`)
- **Output:** Each cluster represents a set of coreferent entity mentions (same real-world entity)

## 5. KNOWLEDGE GRAPH
- **Nodes:** Resolved clusters from Agent 2 (each node = one real-world entity)
  - Properties: `node_id` (cluster ID), `canonical_name`, `entity_type`, `confidence`
- **Edges:** Resolved triples from Agent 2 (subject-predicate-object → subject_cluster → predicate → object_cluster)
  - Properties: `predicate` (relationship type), `confidence`, `is_predicted` (bool)
- **Connection Process:**
  - Evidence → Agent 1 Entities/Triples → Agent 2 Clusters/ResolvedTriples → Agent 3 Nodes/Edges
  - Clusters become nodes; resolved triples become edges
- **Evidence Connection:** 
  - Nodes store lists of source entity IDs and evidence IDs
  - Edges store original triple ID and evidence context (timestamp, location)
- **Database:** 
  - Agent 3 uses PostgreSQL to retrieve resolved data for graph construction
  - Final graph exported to Neo4j for querying (nodes: `Entity`, relationships: typed by predicate)

## 6. DATABASE
- **Agent 1 Storage:** PostgreSQL
  - `evidence_records`: One per evidence file (evidence_id, hash, raw text)
  - `extracted_entities`: Entity mentions (linked to evidence_id)
  - `extracted_triples`: Subject-predicate-object triples (linked to evidence_id)
- **Agent 2 Storage:** PostgreSQL (separate schema but same instance)
  - `resolution_runs`: One per resolution batch
  - `clusters`: Resolved clusters (ID, centroid vector, entity type)
  - `cluster_mentions`: Many-to-manket between clusters and entity mentions
  - `resolved_triples`: Triples between clusters (subject_cluster_id, predicate, object_cluster_id)
- **Agent 3 Storage:** 
  - Reads from Agent 1 & 2 PostgreSQL to build graph in memory
  - Exports to Neo4j (primary) or NetworkX/JSON
- **Agent 4 Storage:** 
  - Neo4j: Contains the knowledge graph (nodes: `Entity`, relationships: `<predicate>`)
  - PostgreSQL (via Agent 2's repository): Used for vector similarity search (pgvector on cluster centroids)

## 7. LAST AGENT / QUERYING (Agent 4)
- **User Query Entry:** Natural language string via `/api/v1/graphrag/query` (POST/GET)
- **Processing in Agent 4:**
  1. Extracts terms and classifies intent (e.g., "who" → PERSON/ORGANIZATION)
  2. Embeds full query with BGE-m3 → vector
  3. Queries Agent 2's pgvector store for top-k similar clusters (by cosine similarity)
  4. Uses cluster IDs to fetch matching nodes from Neo4j
  5. Finds paths between nodes (shortest path, max length 3) and 1-hop neighborhood
  6. Retrieves detailed node information (IDs, names, types, evidence)
  7. Generates answer: 
     - Template-based summary of nodes and paths
     - Confidence heuristic based on node/path count
     - Optional LLM synthesis for forensic detail (if configured)
- **Retrieval Method:** 
  - Vector search (pgvector) for candidate clusters
  - Neo4j traversal for graph relationships (paths and neighborhood)
- **Final Output:** `GraphRAGResult` with answer, confidence, supporting evidence, related nodes/paths

## 8. FINAL STRUCTURED OUTPUT
Example `GraphRAGResult` structure (from `agent4_graphRAG/models/schemas.py`):
```json
{
  "answer": "Found 2 relevant entities in the Knowledge Graph:\n  • Rajesh Sharma (Type: PERSON, Node/Cluster ID: CLU-00001, Confidence: 1.00)\n  • TechCorp (Type: ORGANIZATION, Node/Cluster ID: CLU-00002, Confidence: 1.00)\n\nConnected Graph Triples & Relationships:\n  • [Rajesh Sharma (ID: CLU-00001)] --[works_for]--> [TechCorp (ID: CLU-00002)]",
  "confidence": 0.5,
  "supporting_evidence": ["EV-FIR_1102_2026-123456"],
  "related_nodes": [
    {
      "node_id": "CLU-00001",
      "canonical_name": "Rajesh Sharma",
      "entity_type": "PERSON",
      "confidence": 1.0,
      "source_entities": [101, 102],
      "evidence_sources": ["EV-FIR_1102_2026-123456"]
    },
    {
      "node_id": "CLU-00002",
      "canonical_name": "TechCorp",
      "entity_type": "ORGANIZATION",
      "confidence": 1.0,
      "source_entities": [201],
      "evidence_sources": ["EV-FIR_1102_2026-123456"]
    }
  ],
  "related_paths": [
    {
      "source": "CLU-00001",
      "target": "CLU-00002",
      "nodes": [
        {"node_id": "CLU-00001", "canonical_name": "Rajesh Sharma", "entity_type": "PERSON"},
        {"node_id": "CLU-00002", "canonical_name": "TechCorp", "entity_type": "ORGANIZATION"}
      ],
      "relationships": [
        {"predicate": "works_for", "confidence": 0.95, "is_predicted": false}
      ]
    }
  ],
  "query_time_ms": 142.5
}
```

## 9. COMPLETE PIPELINE IN ONE VIEW
```
Input Evidence
→ Agent 1 (Extraction) 
→ PostgreSQL (evidence, entities, triples)
→ Agent 2 (Resolution: BGE-m3 + Metaphone + HAC)
→ PostgreSQL (clusters, resolved triples)
→ Agent 3 (Knowledge Graph Build)
→ Neo4j (graph storage)
→ Agent 4 (GraphRAG Query)
→ Structured Output (answer + evidence)
```

## 10. 30-SECOND EXPLANATION
This project processes forensic evidence through four AI agents: first extracting people, organizations, and their relationships from text/images; then resolving duplicate entity mentions using AI embeddings and clustering; next building a knowledge graph from the resolved entities; finally enabling natural language questions like "Who works at TechCorp?" that search the graph and return answers with supporting evidence. The system combines symbolic AI (regex, rules) with neural AI (embeddings, LLMs) to create an auditable, question-ready knowledge base from raw investigative data.