"""
pipeline.py — Main pipeline for Agent 3 Knowledge Graph Builder
Responsibility: Build knowledge graph from Agent 1 & 2 data, export to various formats.
"""

import time
import json
from typing import Optional, Dict, Any
from loguru import logger

from agent3_graph.storage.database import GraphRepository
from agent3_graph.models.schemas import KnowledgeGraph
from agent3_graph.exporters.neo4j_exporter import Neo4jExporter
from agent3_graph.exporters.networkx_exporter import NetworkxExporter


class KnowledgeGraphPipeline:
    """Orchestrator for building and exporting knowledge graphs."""

    def __init__(self):
        self.repository = GraphRepository()
        self.neo4j_exporter = Neo4jExporter()
        self.networkx_exporter = NetworkxExporter()

    def build_graph(self, run_id: str) -> KnowledgeGraph:
        """
        Build a knowledge graph from Agent 1 & 2 data for a given resolution run.
        """
        start_time = time.time()

        logger.info(f"Building knowledge graph for resolution run: {run_id}")

        try:
            # Build the knowledge graph
            knowledge_graph = self.repository.build_knowledge_graph(run_id)

            execution_time = round((time.time() - start_time) * 1000, 2)

            logger.info(
                f"Knowledge graph built successfully: {knowledge_graph.graph_id} "
                f"({knowledge_graph.node_count} nodes, {knowledge_graph.edge_count} edges) "
                f"in {execution_time}ms"
            )

            return knowledge_graph

        except Exception as e:
            logger.error(f"Failed to build knowledge graph for run {run_id}: {e}")
            raise

    def export_to_neo4j(self, graph: KnowledgeGraph) -> bool:
        """Export knowledge graph to Neo4j database."""
        try:
            success = self.neo4j_exporter.export_graph(graph)
            if success:
                logger.info(f"Exported graph {graph.graph_id} to Neo4j successfully")
            else:
                logger.warning(f"Failed to export graph {graph.graph_id} to Neo4j")
            return success
        except Exception as e:
            logger.error(f"Neo4j export failed for graph {graph.graph_id}: {e}")
            return False

    def export_to_networkx(self, graph: KnowledgeGraph) -> Optional[Any]:
        """Export knowledge graph to NetworkX graph object."""
        try:
            nx_graph = self.networkx_exporter.export_graph(graph)
            logger.info(f"Exported graph {graph.graph_id} to NetworkX successfully")
            return nx_graph
        except Exception as e:
            logger.error(f"NetworkX export failed for graph {graph.graph_id}: {e}")
            return None

    def export_as_json(self, graph: KnowledgeGraph) -> str:
        """Export knowledge graph as JSON string."""
        try:
            json_str = graph.json(indent=2)
            logger.info(f"Exported graph {graph.graph_id} as JSON successfully")
            return json_str
        except Exception as e:
            logger.error(f"JSON export failed for graph {graph.graph_id}: {e}")
            raise

    def build_and_export(
        self,
        run_id: str,
        export_formats: list[str] = ["json"]
    ) -> Dict[str, Any]:
        """
        Build a knowledge graph and export to specified formats.

        Args:
            run_id: Agent 2 resolution run ID
            export_formats: List of formats to export to ["json", "neo4j", "networkx"]

        Returns:
            Dict containing graph metadata and export results
        """
        result = {
            "run_id": run_id,
            "graph_id": None,
            "exports": {},
            "statistics": {},
        }

        try:
            # Build the graph
            graph = self.build_graph(run_id)
            result["graph_id"] = graph.graph_id
            result["statistics"] = {
                "node_count": graph.node_count,
                "edge_count": graph.edge_count,
                "timestamp": graph.created_at,
            }

            # Export to requested formats
            for fmt in export_formats:
                if fmt == "json":
                    result["exports"]["json"] = self.export_as_json(graph)
                elif fmt == "neo4j":
                    result["exports"]["neo4j"] = self.export_to_neo4j(graph)
                elif fmt == "networkx":
                    nx_graph = self.export_to_networkx(graph)
                    if nx_graph:
                        result["exports"]["networkx"] = "success"
                else:
                    logger.warning(f"Unknown export format: {fmt}")

            logger.info(f"Build and export completed for run {run_id}")
            return result

        except Exception as e:
            logger.error(f"Build and export failed for run {run_id}: {e}")
            raise