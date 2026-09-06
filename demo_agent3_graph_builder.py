#!/usr/bin/env python3
"""
demo_agent3_graph_builder.py

End-to-end demo of Agent 3 (Graph Builder Pro):
1. Uses Agent 2 resolution output (or creates a mock run)
2. Builds knowledge graph
3. Demonstrates link prediction with pgvector
4. Exports to different formats
"""

import time
from loguru import logger

from agent1_extraction.pipeline import UniversalExtractionPipeline
from agent2_resolution.pipeline import EntityResolutionPipeline
from agent3_graph.pipeline import KnowledgeGraphPipeline

# Configure logging
logger.add("demo_agent3.log", level="INFO", rotation="1 MB")


def demo_full_pipeline():
    """End-to-end demo: Agent 1 → Agent 2 → Agent 3 (with link prediction)."""

    print("\n" + "=" * 80)
    print("AGENT 3 GRAPH BUILDER PRO - END-TO-END DEMO")
    print("=" * 80)

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 1: Agent 1 - Extract entities and triples
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "─" * 80)
    print("PHASE 1: Agent 1 - Extract Entities and Triples")
    print("─" * 80)

    agent1 = UniversalExtractionPipeline()

    # Sample documents
    sample_docs = [
        {
            "evidence_id": "EV-001",
            "content": "Rajesh Sharma works at TechCorp in Mumbai. He collaborates with Priya Malhotra.",
            "filename": "doc1.txt"
        },
        {
            "evidence_id": "EV-002",
            "content": "R. Sharma is based in Mumbai City. Priya Malhotra also works there.",
            "filename": "doc2.txt"
        },
    ]

    extraction_payloads = []
    for doc in sample_docs:
        print(f"\nExtracting from {doc['filename']}...")
        start = time.time()
        payload = agent1.process(
            evidence_id=doc["evidence_id"],
            raw_content=doc["content"],
            filename=doc["filename"]
        )
        elapsed = (time.time() - start) * 1000
        print(f"  ✓ Extracted {len(payload.entities)} entities, {len(payload.triples)} triples ({elapsed:.1f}ms)")
        extraction_payloads.append(payload)

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 2: Agent 2 - Resolve entities into clusters
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "─" * 80)
    print("PHASE 2: Agent 2 - Entity Resolution")
    print("─" * 80)

    agent2 = EntityResolutionPipeline()

    print("\nResolving entities across documents...")
    start = time.time()
    resolution = agent2.process(extraction_payloads)
    elapsed = resolution.execution_time_ms

    print(f"  ✓ Resolution complete in {elapsed:.2f}ms")
    print(f"  Clusters: {len(resolution.clusters)}")
    print(f"  Pending Review: {len(resolution.pending_review)}")

    for cluster in resolution.clusters:
        print(f"    - {cluster.cluster_id}: '{cluster.canonical}' ({len(cluster.members)} mentions)")

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 3: Agent 3 - Build Knowledge Graph
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "─" * 80)
    print("PHASE 3: Agent 3 - Knowledge Graph Builder")
    print("─" * 80)

    agent3 = KnowledgeGraphPipeline()

    # 3a. Build graph WITHOUT predictions
    print("\n3a. Building graph WITHOUT link prediction...")
    start = time.time()
    graph_no_pred = agent3.build_graph(resolution.run_id, include_predictions=False)
    elapsed = (time.time() - start) * 1000

    print(f"  ✓ Graph built in {elapsed:.1f}ms")
    print(f"  Nodes: {graph_no_pred.node_count}")
    print(f"  Edges (real): {graph_no_pred.edge_count}")

    # 3b. Build graph WITH predictions
    print("\n3b. Building graph WITH link prediction...")
    start = time.time()
    graph_with_pred = agent3.build_graph(resolution.run_id, include_predictions=True)
    elapsed = (time.time() - start) * 1000

    real_edges = sum(1 for edge in graph_with_pred.edges if not edge.is_predicted)
    predicted_edges = sum(1 for edge in graph_with_pred.edges if edge.is_predicted)

    print(f"  ✓ Graph built in {elapsed:.1f}ms")
    print(f"  Nodes: {graph_with_pred.node_count}")
    print(f"  Edges (real): {real_edges}")
    print(f"  Edges (predicted): {predicted_edges}")
    print(f"  Total edges: {graph_with_pred.edge_count}")

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 4: Graph Analysis
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "─" * 80)
    print("PHASE 4: Graph Analysis")
    print("─" * 80)

    print("\nNodes in graph:")
    for node in graph_with_pred.nodes:
        print(f"  • {node.node_id}: {node.canonical_name} ({node.entity_type})")
        print(f"    Confidence: {node.confidence:.2f}, Evidence: {node.evidence_sources}")

    print("\nEdges in graph:")
    for edge in graph_with_pred.edges:
        pred_label = "[PREDICTED]" if edge.is_predicted else "[REAL]"
        source_node = graph_with_pred.get_node_by_id(edge.source_node)
        target_node = graph_with_pred.get_node_by_id(edge.target_node)
        source_name = source_node.canonical_name if source_node else edge.source_node
        target_name = target_node.canonical_name if target_node else edge.target_node
        print(f"  {pred_label} {source_name} --[{edge.predicate}]--> {target_name} (conf: {edge.confidence:.2f})")

    # ════════════════════════════════════════════════════════════════════════════════
    # PHASE 5: Export
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "─" * 80)
    print("PHASE 5: Export Formats")
    print("─" * 80)

    # JSON export
    print("\nExporting to JSON...")
    json_str = agent3.export_as_json(graph_with_pred)
    print(f"  ✓ JSON export complete ({len(json_str)} bytes)")

    # NetworkX export
    print("\nExporting to NetworkX...")
    nx_graph = agent3.export_to_networkx(graph_with_pred)
    if nx_graph:
        print(f"  ✓ NetworkX export complete: {nx_graph.number_of_nodes()} nodes, {nx_graph.number_of_edges()} edges")

    # ════════════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"""
Agent 1 (Extraction):
  - Processed {len(sample_docs)} documents
  - Extracted {sum(len(p.entities) for p in extraction_payloads)} entities
  - Extracted {sum(len(p.triples) for p in extraction_payloads)} relationships

Agent 2 (Resolution):
  - Created {len(resolution.clusters)} entity clusters
  - {len(resolution.pending_review)} pairs pending review
  - Stored BGE-m3 centroid embeddings in pgvector

Agent 3 (Graph Builder Pro):
  - Built knowledge graph with {graph_with_pred.node_count} nodes
  - Real edges: {real_edges}
  - Predicted edges (pgvector): {predicted_edges}
  - Total edges: {graph_with_pred.edge_count}

Link Prediction Algorithm:
  - Uses centroid embeddings from Agent 2 (pgvector)
  - Computes pairwise cosine similarity
  - Creates edges for similarity > LINK_PREDICTION_THRESHOLD (0.85)
  - Marks predictions with is_predicted=true for Neo4j queries

Export Formats:
  - JSON: Direct serialization
  - Neo4j: Graph database export (with is_predicted flag)
  - NetworkX: In-memory graph analysis
  - GraphML: Visualization tools
    """)


def demo_with_predictions_only():
    """Quick demo showing just the link prediction feature."""

    print("\n" + "=" * 80)
    print("AGENT 3 LINK PREDICTION - FEATURE DEMO")
    print("=" * 80)

    print("\nLink Prediction uses pgvector centroid embeddings to find similar entities.")
    print("This enables predicting missing relationships without re-clustering.\n")

    # This would need a pre-existing resolution run_id
    # For demo purposes, we show the concept
    print("Concept:")
    print("  1. Agent 2 stores BGE-m3 centroid embeddings (1024-dim) in pgvector")
    print("  2. Agent 3 queries pgvector: cosine_similarity(embedding_A, embedding_B)")
    print("  3. If similarity > threshold AND no existing edge: create predicted edge")
    print("  4. Mark edge with is_predicted=true in Neo4j for easy filtering\n")

    print("Configuration:")
    print("  INCLUDE_PREDICTIONS: Toggle prediction on/off")
    print("  LINK_PREDICTION_THRESHOLD: Min similarity for prediction (default 0.85)")
    print("  PREDICTION_MIN_CONFIDENCE: Min confidence to keep (default 0.70)\n")

    print("Neo4j Queries:")
    print("  # Get only real edges")
    print("  MATCH (s)-[r:RELATION]->(t) WHERE r.is_predicted = false RETURN s, r, t\n")
    print("  # Get only predicted edges")
    print("  MATCH (s)-[r:RELATION]->(t) WHERE r.is_predicted = true RETURN s, r, t")


if __name__ == "__main__":
    try:
        # Run full pipeline demo
        demo_full_pipeline()

        # Show link prediction concept
        print("\n")
        demo_with_predictions_only()

        print("\n" + "=" * 80)
        print("DEMO COMPLETE")
        print("=" * 80 + "\n")

    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"\nDemo failed: {e}\n")
