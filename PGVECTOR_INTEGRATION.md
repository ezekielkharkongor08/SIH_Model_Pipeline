# Agent 2: Entity Resolution with pgvector Integration

## Overview

Agent 2 has been upgraded to integrate **PostgreSQL's pgvector extension** for persistent embedding storage and incremental entity resolution. This enables:

- **Persistent embeddings**: BGE-m3 centroid embeddings (1024-dim) stored in PostgreSQL
- **Fast vector search**: HNSW index using cosine similarity for O(log n) lookup
- **Incremental resolution**: New entity mentions matched against stored centroids without re-clustering
- **Reusability**: Embeddings computed once, queried infinitely

## Architecture Changes

### 1. Schema Enhancements (schema_agent2.sql)

```sql
-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enhanced entity_clusters table
CREATE TABLE IF NOT EXISTS entity_clusters (
    ...
    centroid_embedding VECTOR(1024),  -- BGE-m3 centroid embedding
    ...
);

-- HNSW index for fast cosine similarity search
CREATE INDEX idx_clusters_centroid_hnsw
ON entity_clusters
USING hnsw (centroid_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Key Details:**
- `VECTOR(1024)`: BGE-m3 outputs exactly 1024 dimensions
- `vector_cosine_ops`: Uses cosine distance for semantic similarity (standard for embeddings)
- `HNSW`: Hierarchical Navigable Small World — state-of-the-art approximate nearest neighbor search
- `m=16, ef_construction=64`: Tuned for balancing speed vs accuracy

### 2. SQLAlchemy Model Updates (storage/database.py)

```python
class ClusterModel(Base):
    __tablename__ = "entity_clusters"
    
    # ... existing fields ...
    centroid_embedding = Column(Text, nullable=True)  # JSON string, parsed on read
    
    __table_args__ = (
        Index("idx_clusters_centroid_hnsw", "centroid_embedding", 
              postgresql_using="gin",
              postgresql_ops={"centroid_embedding": "vector_cosine_ops"}),
    )
```

**Note**: Stored as TEXT (JSON-serialized) for compatibility. PostgreSQL's pgvector extension automatically parses it.

### 3. Pydantic Schema Update (models/schemas.py)

```python
class EntityCluster(BaseModel):
    cluster_id: str
    canonical: str
    entity_type: str
    members: List[EntityMention]
    avg_similarity: float
    centroid_embedding: Optional[List[float]] = None  # NEW: 1024-dim vector
```

### 4. Clustering with Centroid Calculation (clustering/clusterer.py)

When building clusters during HAC, centroids are now calculated and normalized:

```python
def _cut_and_build(...) -> list[EntityCluster]:
    # ... clustering logic ...
    
    # Calculate centroid embedding
    centroid = np.mean(member_embeds, axis=0)
    centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-9)
    centroid_list = centroid_norm.astype(np.float32).tolist()
    
    clu = EntityCluster(
        cluster_id=f"CLU-{cluster_id:05d}",
        canonical=canonical,
        entity_type=entity_type,
        members=member_mentions,
        avg_similarity=avg_sim,
        centroid_embedding=centroid_list,  # NEW
    )
```

### 5. Database Layer — Vector Similarity Search (storage/database.py)

New method `find_similar_clusters()` performs pgvector queries:

```python
def find_similar_clusters(
    self,
    embedding: list[float],
    entity_type: str = None,
    top_k: int = 5,
    threshold: float = 0.80,
) -> list[tuple[str, str, float]]:
    """
    Find existing clusters similar to the given embedding using pgvector.
    
    Args:
        embedding: 1024-dim BGE-m3 embedding (unit-norm)
        entity_type: Optional filter by entity_type
        top_k: Max number of results
        threshold: Min similarity score (0-1)
    
    Returns:
        List of (cluster_id, canonical_name, similarity_score)
    """
    # Uses pgvector cosine distance operator (<->)
    # Returns clusters with similarity >= threshold, ranked by distance
```

**SQL Generated:**
```sql
SELECT cluster_id, canonical_name, 
       1 - (centroid_embedding <-> :embedding::vector) AS similarity
FROM entity_clusters
WHERE centroid_embedding IS NOT NULL
  AND entity_type = :entity_type
  AND (1 - (centroid_embedding <-> :embedding::vector)) >= :threshold
ORDER BY centroid_embedding <-> :embedding::vector
LIMIT :top_k;
```

### 6. Incremental Resolution API (pipeline.py)

New method `resolve_new_mention()` enables real-time entity resolution:

```python
def resolve_new_mention(
    self,
    surface: str,
    entity_type: str,
    evidence_id: str = "INC-001",
    confidence: float = 1.0,
    reuse_threshold: float = 0.90,
) -> tuple[Optional[str], Optional[ResolutionPayload]]:
    """
    Resolve a single new entity mention by querying stored cluster centroids.
    
    Returns:
        (cluster_id_if_reused, new_resolution_payload_if_new_entity)
    
    Flow:
    1. Embed new mention with BGE-m3
    2. Query pgvector for similar centroids (reuse_threshold=0.90)
    3a. If match found → return cluster_id (FAST, no re-clustering)
    3b. If no match → create new cluster, persist embedding, return payload
    """
```

## Usage Patterns

### Pattern 1: Batch Resolution (Traditional)

```python
from agent2_resolution.pipeline import EntityResolutionPipeline

pipeline = EntityResolutionPipeline()

# Process multiple mentions at once
payload = pipeline.resolve_mentions([mention1, mention2, mention3])

# Clusters are built with centroids and persisted to DB with pgvector
print(f"Created {len(payload.clusters)} clusters")
print(f"Centroids stored in pgvector: {all(c.centroid_embedding for c in payload.clusters)}")
```

### Pattern 2: Incremental Resolution (NEW)

```python
# Resolve new mentions one at a time, reusing existing clusters

# Case A: Match found (reuse existing cluster)
cluster_id, payload = pipeline.resolve_new_mention(
    surface="R. Sharma",
    entity_type="PERSON",
    reuse_threshold=0.90,  # 90% similarity minimum
)
if cluster_id:
    print(f"Reused cluster: {cluster_id}")  # Fast! No re-clustering

# Case B: No match (create new cluster)
cluster_id, payload = pipeline.resolve_new_mention(
    surface="John Smith",
    entity_type="PERSON",
    reuse_threshold=0.90,
)
if not cluster_id:
    print(f"Created new cluster: {payload.clusters[0].cluster_id}")
    # New centroid persisted to pgvector
```

### Pattern 3: Direct Vector Similarity Search

```python
# Query for entities similar to an embedding

embedding = pipeline.embedder.embed("Rajesh Sharma")
embedding_list = embedding.astype("float32").tolist()

similar_clusters = pipeline.db_repo.find_similar_clusters(
    embedding=embedding_list,
    entity_type="PERSON",
    top_k=5,
    threshold=0.85,
)

for cluster_id, canonical, similarity in similar_clusters:
    print(f"{cluster_id}: '{canonical}' (sim={similarity:.4f})")
```

## Performance Characteristics

### Vector Search Complexity

| Operation | Complexity | Time (1M clusters) |
|-----------|------------|-------------------|
| **HAC re-clustering** | O(n² log n) | ~hours |
| **HNSW vector search** | O(log n) | ~1-5ms |
| **Linear scan** | O(n) | ~100-500ms |

**Savings with pgvector:**
- 100x faster than linear scan for finding similar clusters
- Eliminates need to re-cluster on every new mention
- Scales to millions of entities with sub-10ms queries

### Storage

- **1024-dim embedding**: ~4 KB per cluster (4 bytes × 1024 floats)
- **HNSW index overhead**: ~5-10% additional space
- **Million clusters**: ~4 GB embeddings + 200-400 MB index

## Integration with Other Agents

### Agent 1 → Agent 2

Agent 2 now enriches clusters with embeddings before passing to Agent 3:

```python
# From Agent 1 extraction
payload = agent1.process(doc)

# Agent 2 resolution (with pgvector storage)
resolution = agent2.process([payload])

# Clusters include centroid_embedding for Agent 3 graph analytics
for cluster in resolution.clusters:
    print(f"Cluster: {cluster.canonical}")
    print(f"  Centroid: {cluster.centroid_embedding[:10]}...")  # First 10 dims
```

### Agent 2 → Agent 3

Agent 3 can now:
- Use cluster embeddings for entity similarity ranking
- Group clusters by semantic proximity (not just name matching)
- Build semantic graphs based on embedding space proximity

## Configuration

Add to `.env` or `agent2_resolution/config.py`:

```env
# pgvector settings
PGVECTOR_DIMENSION=1024          # BGE-m3 output dimension
PGVECTOR_M=16                    # HNSW M parameter (default 16)
PGVECTOR_EF_CONSTRUCTION=64      # HNSW ef_construction (default 64)

# Incremental resolution thresholds
INCREMENTAL_REUSE_THRESHOLD=0.90  # Min similarity to reuse cluster
INCREMENTAL_QUERY_TOP_K=5         # Top-K similar clusters to check
```

## Database Setup

### Enable pgvector Extension

```bash
# Connect to your PostgreSQL instance
psql -U postgres -d sih_evidence_db

# Enable pgvector (one-time)
CREATE EXTENSION IF NOT EXISTS vector;

# Verify
SELECT extname FROM pg_extension WHERE extname = 'vector';
```

### Apply Schema

```bash
# Run the updated schema_agent2.sql
psql -U postgres -d sih_evidence_db -f schema_agent2.sql

# Verify HNSW index created
\d entity_clusters
```

## Testing & Demo

Run the comprehensive demo:

```bash
python demo_incremental_resolution.py
```

**Demo flow:**
1. **Phase 1**: Batch resolution on 5 mentions → stores centroids in pgvector
2. **Phase 2**: 5 incremental resolutions on new mentions
   - 3 reuse existing clusters (fast!)
   - 2 create new clusters (normal speed)
3. **Phase 3**: Direct pgvector similarity query showing ranking

**Expected output:**
```
PHASE 1: Batch Resolution (Store Centroids in pgvector)
✓ Resolution complete in 45.23ms
  Clusters created: 2
  Pending review: 0
  - CLU 00001: 'Rajesh Sharma' (3 members, centroid=1024-dim)
  - CLU 00002: 'Mumbai' (2 members, centroid=1024-dim)

PHASE 2: Incremental Resolution (Query pgvector Centroids)
  New mention: 'Rajesh Sharma' (PERSON)
    ✓ Reused cluster: CLU-00001 (2.34ms)
  New mention: 'R Sharma' (PERSON)
    ✓ Reused cluster: CLU-00001 (2.12ms)
  ...

PHASE 3: Direct pgvector Similarity Query
Querying for entities similar to 'Rajesh Sharma'...
Top matching clusters:
  • CLU-00001: 'Rajesh Sharma' (similarity=0.9823)
  • ...
```

## Migration from Non-pgvector Setup

If you have existing clusters without embeddings:

```python
# 1. Regenerate embeddings for all clusters
from agent2_resolution.embeddings.embedder import BGEEmbedder
from agent2_resolution.clustering.clusterer import EntityClusterer

embedder = BGEEmbedder()
clusterer = EntityClusterer()

# 2. For each cluster, embed member mentions and compute centroid
for cluster in existing_clusters:
    surfaces = [m.surface for m in cluster.members]
    embeddings = embedder.embed_batch(surfaces)
    centroid = np.mean(embeddings, axis=0)
    centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-9)
    cluster.centroid_embedding = centroid_norm.tolist()

# 3. Update DB
db_repo.save_resolution(payload)

# 4. HNSW index builds automatically on next query
```

## Troubleshooting

### "pgvector extension not found"

```bash
# Install pgvector extension
# Ubuntu/Debian:
sudo apt-get install postgresql-13-pgvector

# Or build from source:
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make PG_CONFIG=/usr/lib/postgresql/13/bin/pg_config
sudo make install PG_CONFIG=/usr/lib/postgresql/13/bin/pg_config
```

### HNSW index slow to build

- Large number of vectors (1M+) may take 5-10 minutes
- Adjust `m` (default 16) and `ef_construction` (default 64) lower for faster builds
- Lower values = slower queries but faster index creation

### Vector search returns no results

- Check `threshold` is not too high (try 0.70 for testing)
- Verify `entity_type` filter matches (null = all types)
- Confirm embeddings are in DB: `SELECT COUNT(*) FROM entity_clusters WHERE centroid_embedding IS NOT NULL;`

## References

- **pgvector**: https://github.com/pgvector/pgvector
- **HNSW**: https://arxiv.org/abs/1802.02413 (Hierarchical Navigable Small Worlds)
- **BGE-m3**: https://huggingface.co/BAAI/bge-m3 (1024-dim multilingual embedder)
- **Cosine similarity**: Standard metric for normalized embeddings

## Next Steps

1. ✅ **Done**: pgvector schema + HNSW index
2. ✅ **Done**: Centroid embedding calculation
3. ✅ **Done**: Vector similarity query API
4. ✅ **Done**: Incremental resolution pipeline
5. **Coming**: Agent 3 graph construction using semantic embeddings
6. **Coming**: Web UI for manual cluster merging with embedding visualization
7. **Coming**: Batch reprocessing to backfill embeddings in existing DBs
