import os
import re
import json
from typing import List, Dict, Any, Set, Tuple
import networkx as nx
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import GraphNode, GraphEdge, KnowledgeGraphResponse

class KnowledgeGraphEngine:
    """Production Knowledge Graph engine with entity extraction, NetworkX graph modeling, and traversal."""
    def __init__(self, storage_path: str = settings.GRAPH_STORAGE_PATH):
        self.storage_path = storage_path
        self.graph = nx.DiGraph()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for node in data.get("nodes", []):
                    self.graph.add_node(
                        node["id"],
                        name=node.get("name", node["id"]),
                        entity_type=node.get("entity_type", "CONCEPT"),
                        attributes=node.get("attributes", {})
                    )
                for edge in data.get("edges", []):
                    self.graph.add_edge(
                        edge["source"],
                        edge["target"],
                        relation=edge.get("relation", "relates_to"),
                        weight=edge.get("weight", 1.0)
                    )
                logger.info(f"Loaded Knowledge Graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
            except Exception as e:
                logger.warning(f"Error loading knowledge graph: {e}")

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            nodes = []
            for n, d in self.graph.nodes(data=True):
                nodes.append({
                    "id": n,
                    "name": d.get("name", n),
                    "entity_type": d.get("entity_type", "CONCEPT"),
                    "attributes": d.get("attributes", {})
                })
            edges = []
            for u, v, d in self.graph.edges(data=True):
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", "relates_to"),
                    "weight": d.get("weight", 1.0)
                })
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"nodes": nodes, "edges": edges}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving knowledge graph: {e}")

    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """Domain entity extraction for tech, orgs, algorithms, concepts."""
        entities = []
        # Tech and Architecture patterns
        patterns = {
            "TECHNOLOGY": [
                r"\b(ChromaDB|Qdrant|PostgreSQL|FastAPI|Docker|Python|NetworkX|Presidio|PyTorch|BM25|Hugging\s*Face)\b",
                r"\b(MiniLM|Cross-Encoder|SentenceTransformers|LangChain|LlamaIndex|Docling)\b",
            ],
            "CONCEPT": [
                r"\b(Hybrid Search|Reciprocal Rank Fusion|RRF|Vector Search|Dense Embedding|Sparse Retrieval|Semantic Search)\b",
                r"\b(PII Guardrails|Prompt Injection|Faithfulness|Groundedness|Reranking|HyDE|Context Deduplication)\b",
                r"\b(Knowledge Graph|Entity Extraction|Graph Traversal)\b"
            ],
            "ORGANIZATION": [
                r"\b(Google|DeepMind|Meta|OpenAI|Microsoft|Anthropic|Chroma|Hugging Face)\b"
            ]
        }
        seen = set()
        for etype, regexes in patterns.items():
            for r in regexes:
                matches = re.finditer(r, text, re.IGNORECASE)
                for m in matches:
                    val = m.group(1).strip()
                    std_val = val.title()
                    if std_val.lower() not in seen:
                        seen.add(std_val.lower())
                        entities.append({"name": std_val, "type": etype})

        # Capitalized acronyms (3-5 letters)
        acronyms = re.findall(r"\b[A-Z]{3,5}\b", text)
        for acr in acronyms:
            if acr.lower() not in seen and acr not in ["THE", "AND", "FOR", "NOT"]:
                seen.add(acr.lower())
                entities.append({"name": acr, "type": "CONCEPT"})

        return entities

    def add_entities_and_relations(self, text: str, document_id: str):
        """Extracts entities from text chunk and builds co-occurrence relational edges."""
        extracted = self.extract_entities(text)
        if len(extracted) < 1:
            return

        # Add nodes
        for ent in extracted:
            nid = ent["name"].lower().replace(" ", "_")
            if not self.graph.has_node(nid):
                self.graph.add_node(
                    nid,
                    name=ent["name"],
                    entity_type=ent["type"],
                    attributes={"doc_sources": [document_id]}
                )
            else:
                docs = self.graph.nodes[nid].get("attributes", {}).get("doc_sources", [])
                if document_id not in docs:
                    docs.append(document_id)

        # Add pairwise relations if co-occurring in same text
        for i in range(len(extracted)):
            for j in range(i + 1, len(extracted)):
                u = extracted[i]["name"].lower().replace(" ", "_")
                v = extracted[j]["name"].lower().replace(" ", "_")
                if u != v:
                    if self.graph.has_edge(u, v):
                        self.graph[u][v]["weight"] = self.graph[u][v].get("weight", 1.0) + 0.5
                    else:
                        rel = "associated_with"
                        if extracted[i]["type"] == "TECHNOLOGY" and extracted[j]["type"] == "CONCEPT":
                            rel = "implements"
                        elif extracted[i]["type"] == "ORGANIZATION" and extracted[j]["type"] == "TECHNOLOGY":
                            rel = "created_by"
                        self.graph.add_edge(u, v, relation=rel, weight=1.0)

        self.save()

    def traverse_subgraph(self, query: str, max_depth: int = 2) -> List[str]:
        """Finds entities in query and traverses graph neighbors to extract relational context facts."""
        extracted = self.extract_entities(query)
        if not extracted:
            return []

        relational_facts: List[str] = []
        visited_nodes: Set[str] = set()

        for ent in extracted:
            nid = ent["name"].lower().replace(" ", "_")
            if self.graph.has_node(nid):
                visited_nodes.add(nid)
                # Successors
                for neighbor in self.graph.successors(nid):
                    edge_data = self.graph.get_edge_data(nid, neighbor)
                    rel = edge_data.get("relation", "relates to")
                    neighbor_name = self.graph.nodes[neighbor].get("name", neighbor)
                    relational_facts.append(f"{ent['name']} {rel.replace('_', ' ')} {neighbor_name}.")
                # Predecessors
                for predecessor in self.graph.predecessors(nid):
                    edge_data = self.graph.get_edge_data(predecessor, nid)
                    rel = edge_data.get("relation", "relates to")
                    pred_name = self.graph.nodes[predecessor].get("name", predecessor)
                    relational_facts.append(f"{pred_name} {rel.replace('_', ' ')} {ent['name']}.")

        return list(dict.fromkeys(relational_facts))[:6]

    def get_graph_data(self) -> KnowledgeGraphResponse:
        nodes = []
        for n, d in self.graph.nodes(data=True):
            nodes.append(GraphNode(
                id=n,
                name=d.get("name", n),
                entity_type=d.get("entity_type", "CONCEPT"),
                attributes=d.get("attributes", {})
            ))
        edges = []
        for u, v, d in self.graph.edges(data=True):
            edges.append(GraphEdge(
                source=u,
                target=v,
                relation=d.get("relation", "relates_to"),
                weight=d.get("weight", 1.0)
            ))
        return KnowledgeGraphResponse(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges)
        )

knowledge_graph = KnowledgeGraphEngine()
