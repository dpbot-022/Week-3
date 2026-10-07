from fastapi import APIRouter, Depends
from src.schemas.models import KnowledgeGraphResponse
from src.api.deps import get_knowledge_graph

router = APIRouter(prefix="/graph", tags=["Knowledge Graph & Entities"])

@router.get("", response_model=KnowledgeGraphResponse)
async def get_graph(knowledge_graph=Depends(get_knowledge_graph)):
    """Returns the current NetworkX knowledge graph nodes, edges, and statistics."""
    return knowledge_graph.get_graph_data()
