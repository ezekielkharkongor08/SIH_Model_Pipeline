#!/usr/bin/env python3
"""
run_pipeline_test.py - Complete Pipeline Test for FIR Dataset

Runs all 4 agents on the 20 FIR images and stores results:
- Agent 1: Extract entities & triples from images
- Agent 2: Resolve/cluster entities (deduplication)
- Agent 3: Build knowledge graph
- Agent 4: Query the graph

Outputs stored in: test_results/
"""

import json
import os
import sys
import time
import glob
from datetime import datetime
from pathlib import Path
from loguru import logger
from agent1_extraction.models.schemas import CharacterSpan

# Configure logging to file
LOG_DIR = Path("test_results/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger.add(LOG_DIR / "pipeline_test.log", rotation="10 MB", level="INFO")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Output directories
OUTPUT_DIR = PROJECT_ROOT / "test_results"
AGENT1_OUT = OUTPUT_DIR / "agent1_extraction"
AGENT2_OUT = OUTPUT_DIR / "agent2_resolution"
AGENT3_OUT = OUTPUT_DIR / "agent3_graph"
AGENT4_OUT = OUTPUT_DIR / "agent4_graphrag"

for d in [AGENT1_OUT, AGENT2_OUT, AGENT3_OUT, AGENT4_OUT]:
    d.mkdir(parents=True, exist_ok=True)


def load_fir_images():
    """Load all FIR images from the dataset."""
    fir_dir = PROJECT_ROOT / "fir_dataset"
    images = sorted(fir_dir.glob("*.png"))
    logger.info(f"Found {len(images)} FIR images")
    return images


def run_agent1_extraction(images):
    """
    Agent 1: Universal Extraction
    Process each FIR image and extract entities & triples.
    """
    from agent1_extraction.pipeline import UniversalExtractionPipeline

    logger.info("=" * 60)
    logger.info("AGENT 1: EXTRACTION")
    logger.info("=" * 60)

    pipeline = UniversalExtractionPipeline()
    results = []
    total_entities = 0
    total_triples = 0

    for idx, img_path in enumerate(images, 1):
        logger.info(f"Processing {idx}/20: {img_path.name}")

        with open(img_path, "rb") as f:
            raw_content = f.read()

        try:
            payload = pipeline.process(
                evidence_id=None,
                raw_content=raw_content,
                filename=img_path.name
            )

            results.append({
                "evidence_id": payload.evidence_id,
                "filename": img_path.name,
                "entities_count": len(payload.entities),
                "triples_count": len(payload.triples),
                "execution_time_ms": payload.execution_time_ms,
                "status": payload.status,
                "entities": [
                    {
                        "canonical_name": e.canonical_name,
                        "entity_type": e.entity_type.value if hasattr(e.entity_type, "value") else e.entity_type,
                    }
                    for e in payload.entities
                ],
                "triples": [
                    {
                        "subject": t.subject.canonical_name,
                        "predicate": t.predicate,
                        "object": t.object.canonical_name,
                    }
                    for t in payload.triples
                ]
            })

            total_entities += len(payload.entities)
            total_triples += len(payload.triples)

            logger.info(f"  → {len(payload.entities)} entities, {len(payload.triples)} triples")

        except Exception as e:
            logger.error(f"  → ERROR: {e}")
            results.append({
                "evidence_id": f"ERR-{idx}",
                "filename": img_path.name,
                "status": "FAILED",
                "error": str(e)
            })

    # Save results
    summary = {
        "agent": "Agent 1 - Extraction",
        "timestamp": datetime.now().isoformat(),
        "total_documents": len(images),
        "total_entities_extracted": total_entities,
        "total_triples_extracted": total_triples,
        "avg_entities_per_doc": round(total_entities / len(images), 2) if images else 0,
        "avg_triples_per_doc": round(total_triples / len(images), 2) if images else 0,
    }

    with open(AGENT1_OUT / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    with open(AGENT1_OUT / "extraction_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Agent 1 complete: {total_entities} entities, {total_triples} triples")

    return results, summary


def run_agent2_resolution(agent1_results):
    """
    Agent 2: Entity Resolution
    Cluster entities and deduplicate using BGE-m3 + HAC.
    """
    from agent2_resolution.pipeline import EntityResolutionPipeline
    from agent1_extraction.models.schemas import ExtractionPayload

    logger.info("=" * 60)
    logger.info("AGENT 2: RESOLUTION")
    logger.info("=" * 60)

    # Convert results back to ExtractionPayload objects
    payloads = []
    for r in agent1_results:
        if r.get("status") == "SUCCESS":
            from agent1_extraction.models.schemas import (
                ExtractedEntity, ExtractedTriple, EntityType
            )

            entities = []
            for ent in r.get("entities", []):
                canon_name = ent["canonical_name"]
                try:
                    etype = EntityType(ent["entity_type"])
                except (ValueError, KeyError):
                    etype = EntityType.UNKNOWN

                entities.append(ExtractedEntity(
                    canonical_name=canon_name,
                    entity_type=etype,
                    span=CharacterSpan(start_char=0, end_char=len(canon_name), exact_text=canon_name)
                ))

            triples = []
            for t in r.get("triples", []):
                sub_ent = ExtractedEntity(
                    canonical_name=t["subject"],
                    entity_type=EntityType.UNKNOWN,
                    span=CharacterSpan(start_char=0, end_char=len(t["subject"]), exact_text=t["subject"])
                )
                obj_ent = ExtractedEntity(
                    canonical_name=t["object"],
                    entity_type=EntityType.UNKNOWN,
                    span=CharacterSpan(start_char=0, end_char=len(t["object"]), exact_text=t["object"])
                )
                triples.append(ExtractedTriple(
                    subject=sub_ent,
                    predicate=t["predicate"],
                    object=obj_ent,
                    confidence=0.95
                ))

            payloads.append(ExtractionPayload(
                evidence_id=r["evidence_id"],
                evidence_hash="",
                input_format="IMAGE",
                entities=entities,
                triples=triples,
                execution_time_ms=0,
                status="SUCCESS"
            ))

    # Run resolution
    pipeline = EntityResolutionPipeline()

    try:
        resolution = pipeline.process(payloads)

        # Build results
        results = {
            "run_id": resolution.run_id,
            "total_mentions": resolution.total_mentions,
            "total_clusters": resolution.total_clusters,
            "total_triples": resolution.total_triples,
            "pending_review_count": len(resolution.pending_review),
            "execution_time_ms": resolution.execution_time_ms,
            "status": resolution.status,
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "canonical_name": c.canonical,
                    "entity_type": c.entity_type,
                    "member_count": len(c.members),
                    "avg_similarity": c.avg_similarity,
                    "members": [m.surface for m in c.members]
                }
                for c in resolution.clusters
            ],
            "pending_review": [
                {
                    "mention_a": p.mention_a,
                    "mention_b": p.mention_b,
                    "similarity": p.similarity,
                    "decision": p.decision.value
                }
                for p in resolution.pending_review
            ]
        }

        # Deduplication metrics
        dedup_ratio = round((1 - resolution.total_clusters / resolution.total_mentions) * 100, 2) if resolution.total_mentions > 0 else 0

        summary = {
            "agent": "Agent 2 - Resolution",
            "timestamp": datetime.now().isoformat(),
            "run_id": resolution.run_id,
            "total_mentions_input": resolution.total_mentions,
            "total_clusters_output": resolution.total_clusters,
            "deduplication_ratio_percent": dedup_ratio,
            "pending_review_pairs": len(resolution.pending_review),
            "resolved_triples": resolution.total_triples,
            "execution_time_ms": resolution.execution_time_ms,
        }

        with open(AGENT2_OUT / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        with open(AGENT2_OUT / "resolution_results.json", "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Agent 2 complete: {resolution.total_clusters} clusters from {resolution.total_mentions} mentions")
        logger.info(f"  Deduplication: {dedup_ratio}% reduction")
        logger.info(f"  Pending review: {len(resolution.pending_review)} pairs")

        return results, summary

    except Exception as e:
        logger.error(f"Agent 2 failed: {e}")
        return {"error": str(e)}, {"error": str(e)}


def run_agent3_graph(agent2_results):
    """
    Agent 3: Knowledge Graph Builder
    Build Neo4j graph from resolved clusters.
    """
    from agent3_graph.pipeline import KnowledgeGraphPipeline

    logger.info("=" * 60)
    logger.info("AGENT 3: GRAPH BUILD")
    logger.info("=" * 60)

    if "error" in agent2_results:
        logger.error("Skipping Agent 3 - Agent 2 failed")
        return {"error": "Skipped"}, {"error": "Skipped"}

    pipeline = KnowledgeGraphPipeline()

    try:
        # Build graph using the run_id from Agent 2
        run_id = agent2_results.get("run_id", "TEST-RUN")

        # Build and export with link prediction disabled for initial run
        result = pipeline.build_and_export(
            run_id=run_id,
            export_formats=["json", "neo4j"],
            include_predictions=False
        )

        summary = {
            "agent": "Agent 3 - Graph Builder",
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "nodes_created": result.get("statistics", {}).get("node_count", 0),
            "edges_created": result.get("statistics", {}).get("edge_count", 0),
            "triples_mapped": result.get("statistics", {}).get("real_edges", 0),
            "predictions_made": result.get("statistics", {}).get("predicted_edges", 0),
            "execution_time_ms": result.get("execution_time_ms", 0),
        }

        with open(AGENT3_OUT / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        with open(AGENT3_OUT / "graph_results.json", "w") as f:
            json.dump(result, f, indent=2)

        logger.info(f"Agent 3 complete: {summary['nodes_created']} nodes, {summary['edges_created']} edges")

        return result, summary

    except Exception as e:
        logger.error(f"Agent 3 failed: {e}")
        # Try alternative - get stats from DB
        try:
            repo = pipeline.db_repo
            stats = repo.get_graph_stats(run_id)
            summary = {
                "agent": "Agent 3 - Graph Builder",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "stats_from_db": stats
            }
            with open(AGENT3_OUT / "summary.json", "w") as f:
                json.dump(summary, f, indent=2)
            return {"stats": stats}, summary
        except:
            return {"error": str(e)}, {"error": str(e)}


def run_agent4_graphrag():
    """
    Agent 4: GraphRAG Query Engine
    Test queries on the built graph.
    """
    from agent4_graphRAG.storage.database import GraphRAGRepository
    from agent4_graphRAG.models.schemas import GraphRAGQuery

    logger.info("=" * 60)
    logger.info("AGENT 4: GRAPHRAG QUERIES")
    logger.info("=" * 60)

    try:
        repo = GraphRAGRepository()

        # Test queries
        test_queries = [
            "Who is mentioned in the FIR documents?",
            "What relationships exist between people?",
            "Show all organizations found",
            "Where did the incident occur?",
            "List all vehicles involved in the incident",
            "Summarize the activities of DarkByte",
            "What money was involved in the extortion?",
            "Who is Ananya Rao and what are they linked to?"
        ]

        results = []
        for q in test_queries:
            try:
                query = GraphRAGQuery(query=q, max_results=5, include_predictions=False)
                result = repo.query_graph(query)

                results.append({
                    "query": q,
                    "success": True,
                    "answer": result.answer if result.answer else "",
                    "confidence": result.confidence,
                    "related_nodes_count": len(result.related_nodes),
                    "related_nodes": result.related_nodes,
                    "related_paths": result.related_paths,
                    "query_time_ms": result.query_time_ms
                })
            except Exception as e:
                results.append({
                    "query": q,
                    "success": False,
                    "error": str(e)
                })

        # Get stats
        stats = repo.stats

        summary = {
            "agent": "Agent 4 - GraphRAG",
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(test_queries),
            "successful_queries": sum(1 for r in results if r.get("success")),
            "total_query_time_ms": sum(r.get("query_time_ms", 0) for r in results),
            "cache_hits": stats.cache_hits,
            "cache_misses": stats.cache_misses,
        }

        with open(AGENT4_OUT / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        with open(AGENT4_OUT / "query_results.json", "w") as f:
            json.dump(results, f, indent=2)

        repo.close()

        logger.info(f"Agent 4 complete: {summary['successful_queries']}/{summary['total_queries']} queries successful")

        return results, summary

    except Exception as e:
        logger.error(f"Agent 4 failed: {e}")
        return [{"query": "N/A", "success": False, "error": str(e)}], {"error": str(e)}


def generate_final_report(agent_summaries):
    """Generate final test report with all metrics."""

    report = {
        "test_name": "FIR Dataset Pipeline Test",
        "timestamp": datetime.now().isoformat(),
        "documents_processed": agent_summaries.get("agent1", {}).get("total_documents", 0),
        "agents": agent_summaries,
        "overall_status": "COMPLETED"
    }

    # Calculate key metrics
    try:
        agent1 = agent_summaries.get("agent1", {})
        agent2 = agent_summaries.get("agent2", {})
        agent3 = agent_summaries.get("agent3", {})
        agent4 = agent_summaries.get("agent4", {})

        report["key_metrics"] = {
            "entities_extracted": agent1.get("total_entities_extracted", 0),
            "triples_extracted": agent1.get("total_triples_extracted", 0),
            "clusters_created": agent2.get("total_clusters_output", 0),
            "deduplication_achieved": agent2.get("deduplication_ratio_percent", 0),
            "pending_review_pairs": agent2.get("pending_review_pairs", 0),
            "graph_nodes": agent3.get("nodes_created", 0),
            "graph_edges": agent3.get("edges_created", 0),
            "queries_successful": agent4.get("successful_queries", 0),
            "total_queries": agent4.get("total_queries", 0),
        }
    except Exception as e:
        logger.warning(f"Could not calculate all metrics: {e}")

    with open(OUTPUT_DIR / "final_report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Documents processed: 20 FIR images")
    print("-" * 40)

    if "key_metrics" in report:
        km = report["key_metrics"]
        print(f"AGENT 1 - Extraction:")
        print(f"  • Entities extracted: {km.get('entities_extracted', 'N/A')}")
        print(f"  • Triples extracted: {km.get('triples_extracted', 'N/A')}")
        print()
        print(f"AGENT 2 - Resolution:")
        print(f"  • Clusters created: {km.get('clusters_created', 'N/A')}")
        print(f"  • Deduplication: {km.get('deduplication_achieved', 'N/A')}%")
        print(f"  • Pending review: {km.get('pending_review_pairs', 'N/A')}")
        print()
        print(f"AGENT 3 - Graph Builder:")
        print(f"  • Graph nodes: {km.get('graph_nodes', 'N/A')}")
        print(f"  • Graph edges: {km.get('graph_edges', 'N/A')}")
        print()
        print(f"AGENT 4 - GraphRAG:")
        print(f"  • Queries: {km.get('queries_successful', 'N/A')}/{km.get('total_queries', 'N/A')}")

    print("=" * 60)
    print(f"Results saved to: {OUTPUT_DIR}")
    print("=" * 60)

    return report


def main():
    """Run complete pipeline test."""
    logger.info("Starting pipeline test...")

    start_time = time.time()
    agent_summaries = {}

    # Load FIR images
    images = load_fir_images()

    if not images:
        logger.error("No FIR images found!")
        return

    # Run Agent 1: Extraction
    try:
        agent1_results, agent1_summary = run_agent1_extraction(images)
        agent_summaries["agent1"] = agent1_summary
    except Exception as e:
        logger.error(f"Agent 1 failed: {e}")
        agent_summaries["agent1"] = {"error": str(e)}
        agent1_results = []

    # Run Agent 2: Resolution
    try:
        agent2_results, agent2_summary = run_agent2_resolution(agent1_results)
        agent_summaries["agent2"] = agent2_summary
    except Exception as e:
        logger.error(f"Agent 2 failed: {e}")
        agent_summaries["agent2"] = {"error": str(e)}
        agent2_results = {"error": str(e)}

    # Run Agent 3: Graph Builder
    try:
        agent3_results, agent3_summary = run_agent3_graph(agent2_results)
        agent_summaries["agent3"] = agent3_summary
    except Exception as e:
        logger.error(f"Agent 3 failed: {e}")
        agent_summaries["agent3"] = {"error": str(e)}

    # Run Agent 4: GraphRAG
    try:
        agent4_results, agent4_summary = run_agent4_graphrag()
        agent_summaries["agent4"] = agent4_summary
    except Exception as e:
        logger.error(f"Agent 4 failed: {e}")
        agent_summaries["agent4"] = {"error": str(e)}

    # Generate final report
    report = generate_final_report(agent_summaries)

    total_time = time.time() - start_time
    logger.info(f"Pipeline test completed in {total_time:.2f} seconds")

    return report


if __name__ == "__main__":
    main()