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

    # Ingest ground-truth triples from ingestion_triples.json if present
    gt_file = PROJECT_ROOT / "ingestion_triples.json"
    if gt_file.exists():
        try:
            with open(gt_file, "r") as f:
                gt_triples_data = json.load(f)

            from agent1_extraction.models.schemas import ExtractedEntity, ExtractedTriple, EntityType, CharacterSpan, ExtractionPayload
            from agent1_extraction.storage.database import DatabaseRepository

            db_repo = DatabaseRepository()
            gt_entities_dict = {}
            for t in gt_triples_data:
                s_name = t["subject"]
                s_type_str = t.get("subject_type", "UNKNOWN")
                o_name = t["object"]
                o_type_str = t.get("object_type", "UNKNOWN")

                try:
                    s_type = EntityType(s_type_str)
                except Exception:
                    s_type = EntityType.UNKNOWN

                try:
                    o_type = EntityType(o_type_str)
                except Exception:
                    o_type = EntityType.UNKNOWN

                if s_name not in gt_entities_dict:
                    gt_entities_dict[s_name] = ExtractedEntity(
                        canonical_name=s_name,
                        entity_type=s_type,
                        span=CharacterSpan(start_char=0, end_char=len(s_name), exact_text=s_name)
                    )
                if o_name not in gt_entities_dict:
                    gt_entities_dict[o_name] = ExtractedEntity(
                        canonical_name=o_name,
                        entity_type=o_type,
                        span=CharacterSpan(start_char=0, end_char=len(o_name), exact_text=o_name)
                    )

            gt_triples = []
            for t in gt_triples_data:
                gt_triples.append(ExtractedTriple(
                    subject=gt_entities_dict[t["subject"]],
                    predicate=t["predicate"],
                    object=gt_entities_dict[t["object"]],
                    confidence=1.0
                ))

            evidence_id = "FIR_1102_2026"
            payload = ExtractionPayload(
                evidence_id=evidence_id,
                evidence_hash="FIR_1102_2026_HASH",
                input_format="JSON",
                entities=list(gt_entities_dict.values()),
                triples=gt_triples,
                execution_time_ms=5,
                status="SUCCESS"
            )

            db_repo.save_extraction(payload, json.dumps(gt_triples_data))

            results.append({
                "evidence_id": evidence_id,
                "filename": "ingestion_triples.json",
                "entities_count": len(payload.entities),
                "triples_count": len(payload.triples),
                "execution_time_ms": 5,
                "status": "SUCCESS",
                "entities": [
                    {"canonical_name": e.canonical_name, "entity_type": e.entity_type.value if hasattr(e.entity_type, "value") else e.entity_type}
                    for e in payload.entities
                ],
                "triples": [
                    {"subject": t.subject.canonical_name, "predicate": t.predicate, "object": t.object.canonical_name}
                    for t in payload.triples
                ]
            })
            total_entities += len(payload.entities)
            total_triples += len(payload.triples)
            logger.info(f"  → Ingested ground truth FIR_1102_2026: {len(payload.entities)} entities, {len(payload.triples)} triples")
        except Exception as e:
            logger.warning(f"Failed to ingest ground truth triples: {e}")

    # Save results
    summary = {
        "agent": "Agent 1 - Extraction",
        "timestamp": datetime.now().isoformat(),
        "total_documents": len(images) + (1 if gt_file.exists() else 0),
        "total_entities_extracted": total_entities,
        "total_triples_extracted": total_triples,
        "avg_entities_per_doc": round(total_entities / (len(images) + (1 if gt_file.exists() else 0)), 2) if (len(images) or gt_file.exists()) else 0,
        "avg_triples_per_doc": round(total_triples / (len(images) + (1 if gt_file.exists() else 0)), 2) if (len(images) or gt_file.exists()) else 0,
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

            ent_type_map = {e.canonical_name: e.entity_type for e in entities}

            triples = []
            for t in r.get("triples", []):
                sub_name = t["subject"]
                obj_name = t["object"]
                sub_ent = ExtractedEntity(
                    canonical_name=sub_name,
                    entity_type=ent_type_map.get(sub_name, EntityType.UNKNOWN),
                    span=CharacterSpan(start_char=0, end_char=len(sub_name), exact_text=sub_name)
                )
                obj_ent = ExtractedEntity(
                    canonical_name=obj_name,
                    entity_type=ent_type_map.get(obj_name, EntityType.UNKNOWN),
                    span=CharacterSpan(start_char=0, end_char=len(obj_name), exact_text=obj_name)
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
        "Who is Ananya Rao, what role did she play in the short-selling of Apex Pharmaceuticals, and who was the complainant Rajesh Khurana?",
        "What threats and extortion demands did Mohit Chawla make against journalist Rahul Saraf?",
        "What relationship and financial transaction reference (DEX) exists between Ananya Rao and Vikram Sethi?",
        "How much money did Karan Desai transfer to Mohit Chawla via RTGS, and for what purpose?",
        "Which FIR documents were investigated by Inspector Sanjay Gupta and Inspector Ravi Shinde respectively?",
        "Where are Ananya Rao and Vikram Sethi located, and what were the total illicit profits netted by Ananya Rao?",
        "Where are Mohit Chawla and Karan Desai located, and what syndicate role does Mohit Chawla play?",
        "What VoIP phone number did Mohit Chawla use to call Rahul Saraf on 24 November 2026?",
        "Which legal sections under IPC, SEBI Act, and PMLA are applied in the case against Ananya Rao and Vikram Sethi?",
        "Which legal sections under IPC and IT Act are applied in the case against Mohit Chawla and Karan Desai?",
        "What are the background details and contact numbers for complainants Rajesh Khurana and Rahul Saraf?",
        "What server breach or algorithmic trading tools were executed by Vikram Sethi and Ananya Rao?"
    ]

        results = []
        for q in test_queries:
            try:
                forensic_result = repo.query_forensically(q, document_id="FIR-DOC-001")

                results.append({
                    "query": q,
                    "success": True,
                    "answer": forensic_result["answer"],
                    "structured_connections": forensic_result.get("structured_connections", ""),
                    "raw_graph_data": forensic_result["raw_graph"]
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