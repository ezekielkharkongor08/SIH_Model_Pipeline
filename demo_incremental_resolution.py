#!/usr/bin/env python3
"""
demo_incremental_resolution.py

Demonstrates the pgvector-enhanced Entity Resolution system:
1. Runs initial resolution on batch of entities
2. Stores clusters with centroid embeddings in pgvector
3. Tests incremental resolution: new mentions matched against stored centroids
4. Shows reuse efficiency (no re-clustering needed when similar entities arrive)
"""

import time
from agent2_resolution.pipeline import EntityResolutionPipeline
from agent2_resolution.models.schemas import EntityMention
from loguru import logger

# Configure logging
logger.add("demo_incremental.log", level="INFO", rotation="1 MB")


def demo_incremental_resolution():
    """End-to-end demo of incremental entity resolution with pgvector."""

    pipeline = EntityResolutionPipeline()

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 1: Initial batch resolution (with embedding storage)
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("PHASE 1: Batch Resolution (Store Centroids in pgvector)")
    print("=" * 80)

    initial_mentions = [
        EntityMention(
            surface="Rajesh Sharma",
            entity_type="PERSON",
            evidence_id="EV-001",
            confidence=0.99,
        ),
        EntityMention(
            surface="R. Sharma",
            entity_type="PERSON",
            evidence_id="EV-002",
            confidence=0.95,
        ),
        EntityMention(
            surface="Rajesh S.",
            entity_type="PERSON",
            evidence_id="EV-003",
            confidence=0.92,
        ),
        EntityMention(
            surface="Mumbai",
            entity_type="LOCATION",
            evidence_id="EV-001",
            confidence=0.98,
        ),
        EntityMention(
            surface="Bombay",
            entity_type="LOCATION",
            evidence_id="EV-002",
            confidence=0.96,
        ),
    ]

    print(f"\nResolving {len(initial_mentions)} mentions...")
    start = time.time()
    initial_payload = pipeline.resolve_mentions(initial_mentions)
    elapsed = initial_payload.execution_time_ms

    print(f"✓ Resolution complete in {elapsed:.2f}ms")
    print(f"  Clusters created: {len(initial_payload.clusters)}")
    print(f"  Pending review: {len(initial_payload.pending_review)}")

    for cluster in initial_payload.clusters:
        centroid_size = (
            len(cluster.centroid_embedding) if cluster.centroid_embedding else 0
        )
        print(
            f"  - CLU {cluster.cluster_id}: '{cluster.canonical}' "
            f"({len(cluster.members)} members, centroid={centroid_size}-dim)"
        )

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 2: Test incremental resolution (new mentions)
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("PHASE 2: Incremental Resolution (Query pgvector Centroids)")
    print("=" * 80)

    test_cases = [
        ("Rajesh Sharma", "PERSON", 0.95),  # Should reuse cluster
        ("R Sharma", "PERSON", 0.90),  # Fuzzy variant
        ("Mumbai City", "LOCATION", 0.92),  # Location variant
        ("Delhi", "LOCATION", 0.98),  # New location (no match)
        ("John Smith", "PERSON", 0.99),  # New person (no match)
    ]

    print("\nProcessing new mentions with incremental resolution:\n")

    for surface, entity_type, confidence in test_cases:
        print(f"  New mention: '{surface}' ({entity_type})")

        start = time.time()
        cluster_id, new_payload = pipeline.resolve_new_mention(
            surface=surface,
            entity_type=entity_type,
            evidence_id=f"INC-{int(time.time()*1000) % 10000}",
            confidence=confidence,
            reuse_threshold=0.88,  # 88% similarity to reuse
        )
        elapsed = (time.time() - start) * 1000

        if cluster_id:
            print(f"    ✓ Reused cluster: {cluster_id} ({elapsed:.2f}ms)")
        else:
            print(
                f"    ✓ New cluster created: {new_payload.clusters[0].cluster_id if new_payload.clusters else 'NONE'} ({elapsed:.2f}ms)"
            )

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 3: Direct vector similarity query
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("PHASE 3: Direct pgvector Similarity Query")
    print("=" * 80)

    # Embed a test mention and query directly
    test_mention = "Rajesh Sharma"
    test_embedding = pipeline.embedder.embed(test_mention)
    test_embedding_list = test_embedding.astype("float32").tolist()

    print(f"\nQuerying for entities similar to '{test_mention}'...")
    print(f"Embedding dimension: {len(test_embedding_list)}\n")

    similar = pipeline.db_repo.find_similar_clusters(
        embedding=test_embedding_list,
        top_k=3,
        threshold=0.85,
    )

    if similar:
        print("Top matching clusters:")
        for cluster_id, canonical, similarity in similar:
            print(f"  • {cluster_id}: '{canonical}' (similarity={similarity:.4f})")
    else:
        print("  (No matches above threshold)")

    # ════════════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("""
✓ pgvector Integration Complete:
  1. Centroid embeddings (1024-dim BGE-m3) stored in PostgreSQL
  2. HNSW index on cosine_ops for fast vector search
  3. Incremental resolution queries existing centroids via similarity
  4. New entities matched against stored clusters without re-clustering

Benefits:
  • Fast: O(log n) vector search vs O(n²) re-clustering
  • Reusable: Embeddings persisted, no regeneration needed
  • Real-time: Incremental entity resolution as new mentions arrive
  • Scalable: HNSW index handles 1M+ embeddings efficiently
    """)


if __name__ == "__main__":
    try:
        demo_incremental_resolution()
        print("\n✓ Demo completed successfully!\n")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"\n✗ Demo failed: {e}\n")
