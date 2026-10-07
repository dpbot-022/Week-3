import pytest
from src.knowledge_graph.graph_store import KnowledgeGraphEngine

def test_knowledge_graph_extraction_and_traversal(tmp_path):
    storage_path = str(tmp_path / "test_kg.json")
    kg = KnowledgeGraphEngine(storage_path=storage_path)
    
    text = "Google develops TensorFlow and ChromaDB implements Vector Search."
    entities = kg.extract_entities(text)
    assert len(entities) >= 2
    
    kg.add_entities_and_relations(text, "doc_test")
    assert kg.graph.number_of_nodes() >= 2
    assert kg.graph.number_of_edges() >= 1

    facts = kg.traverse_subgraph("ChromaDB")
    assert len(facts) >= 1
    assert any("Chroma" in f for f in facts)
