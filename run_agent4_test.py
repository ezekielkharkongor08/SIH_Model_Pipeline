#!/usr/bin/env python3
"""
run_agent4_only.py - Isolated Agent 4 GraphRAG Query Runner

Queries the existing Neo4j knowledge graph using Agent 4 without re-running 
Agents 1 through 3, and saves outputs to test_results/agent4_graphrag/.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from loguru import logger

# Configure logging to file
LOG_DIR = Path("test_results/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger.add(LOG_DIR / "agent4_isolated_test.log", rotation="10 MB", level="INFO")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent if Path(__file__).parent.name == "test_results" else Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Output directory for Agent 4
OUTPUT_DIR = PROJECT_ROOT / "test_results" / "agent4_graphrag"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_isolated_agent4():
    """Execute Agent 4 GraphRAG queries against the existing graph store."""
    from agent4_graphRAG.storage.database import GraphRAGRepository
    from agent4_graphRAG.models.schemas import GraphRAGQuery

    logger.info("=" * 60)
    logger.info("ISOLATED AGENT 4: GRAPHRAG QUERY EXECUTION")
    logger.info("=" * 60)

    try:
        repo = GraphRAGRepository()

        test_queries = [
            # Case 1: Stock Short-Selling & Extortion
            "Who is Ananya Rao, what role did she play in the short-selling of Apex Pharmaceuticals stock, and who was the complainant Rajesh Khurana?",
            "What threats and extortion demands did Mohit Chawla make against journalist Rahul Saraf, and what VoIP number was used?",
            "What financial transaction reference (DEX-2026101588) and relationship exist between Ananya Rao and Vikram Sethi in Lower Parel, Mumbai?",
            "How much money did Karan Desai transfer to Mohit Chawla via RTGS-2026112499, and where are they located in Pune?",

            # Case 2: Ransomware & Counterfeit EV Batteries
            "What email ransom demands were made by 'DarkByte' against Dr. Arvind Patel at Apex Pharmaceuticals HQ in Andheri East, Mumbai?",
            "How were Vikram Sethi and Ananya Rao implicated in the server breach and ransomware deployment at MIDC Andheri East?",
            "What role did floor manager Karan Desai and Mohit Chawla play in the counterfeit EV battery pack operation at Bhosari industrial area?",
            "What cargo trucks, delivery vehicles, or transport logistics were identified at the Nexa EV Motors toll gate in Pune?",

            # Case 3: Deepfake Subsidy Fraud & Telegram Blackmail
            "How did data scientist Ritesh Deshmukh and Suraj Pawar use AI-generated deepfake satellite imagery to embezzle drought-relief subsidies in Nashik?",
            "What blackmail threats involving AI-doctored compromising videos did Suraj Pawar send to Revenue Inspector Sandeep Patil via Telegram?",
            "How much money was transferred from Suraj Pawar to Ritesh Deshmukh via RTGS-2026090488 in Panchavati, Nashik?",

            # Cross-Case Investigations, Vehicles, Syndicates & Legal Sections
            "Which police stations and investigating officers (Inspectors Sanjay Gupta, Ravi Shinde, Vikram Patil, Milind Kulkarni, Prakash Zende, Kavita Raut) handled each FIR case?",
            "What organizations, companies, and criminal syndicates (BSE, Apex Pharmaceuticals, Nexa EV Motors, cyber-extortion syndicate) are referenced across all FIRs?",
            "What physical locations, vehicles, and CCTV evidence were recorded in Andheri East, Bhosari, Chakan, and the Nashik Collectorate main gate?",
            "Which legal sections under the IPC (such as 420, 120B, 384, 468, 285), IT Act (43, 66A, 66D, 66E, 67), SEBI Act, and PMLA apply to each set of accused persons?"
        ]

        results = []
        for idx, q in enumerate(test_queries, 1):
            logger.info(f"Processing Query {idx}/{len(test_queries)}: {q[:50]}...")
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
                logger.error(f"Query failed: {e}")
                results.append({
                    "query": q,
                    "success": False,
                    "error": str(e)
                })

        stats = repo.stats
        summary = {
            "agent": "Agent 4 - GraphRAG (Isolated Run)",
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(test_queries),
            "successful_queries": sum(1 for r in results if r.get("success")),
            "cache_hits": stats.cache_hits,
            "cache_misses": stats.cache_misses,
        }

        with open(OUTPUT_DIR / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        with open(OUTPUT_DIR / "query_results.json", "w") as f:
            json.dump(results, f, indent=2)

        repo.close()

        logger.info(f"Agent 4 isolated run complete: {summary['successful_queries']}/{summary['total_queries']} queries successful.")
        
        print("\n" + "=" * 60)
        print("AGENT 4 ISOLATED QUERY EXECUTION COMPLETE")
        print("=" * 60)
        print(f"  • Successful Queries: {summary['successful_queries']}/{summary['total_queries']}")
        print(f"  • Results stored in: {OUTPUT_DIR}")
        print("=" * 60)

        return results, summary

    except Exception as e:
        logger.error(f"Agent 4 isolated run failed: {e}")
        print(f"Error executing Agent 4: {e}")
        return [], {"error": str(e)}


if __name__ == "__main__":
    run_isolated_agent4()