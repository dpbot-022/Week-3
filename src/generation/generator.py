import httpx
from typing import List, Dict, Any, Optional
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk, Citation

class GroundedGenerator:
    """Production grounded generation service supporting OpenAI, local LLMs, and local synthesis."""

    def __init__(self, provider: str = settings.LLM_PROVIDER, api_key: str = settings.OPENAI_API_KEY):
        self.provider = provider
        self.api_key = api_key

    def generate(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        graph_facts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        citations: List[Citation] = []
        for rank, c in enumerate(context_chunks, start=1):
            snippet = c.content[:150] + "..." if len(c.content) > 150 else c.content
            citations.append(Citation(
                chunk_id=c.id,
                document_id=c.document_id,
                snippet=snippet,
                score=round(c.final_score, 4),
                rank=rank
            ))

        if not context_chunks:
            return {
                "answer": "No relevant documents were found in the knowledge base to answer your question.",
                "citations": []
            }

        if self.provider == "openai" and self.api_key:
            return self._call_openai(query, context_chunks, graph_facts, citations)
        else:
            return self._local_grounded_synthesis(query, context_chunks, graph_facts, citations)

    def _call_openai(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        graph_facts: Optional[List[str]],
        citations: List[Citation]
    ) -> Dict[str, Any]:
        context_text = "\n\n".join([f"[{i+1}] {c.content}" for i, c in enumerate(context_chunks)])
        graph_text = "\n".join([f"- {f}" for f in (graph_facts or [])])

        system_prompt = (
            "You are a Senior AI Assistant. Answer the user query strictly using the provided context passages "
            "and knowledge graph facts. Cite your sources using [1], [2], etc. If the answer is not in the context, "
            "state that clearly without fabricating information."
        )
        user_message = f"Query: {query}\n\nContext Passages:\n{context_text}\n"
        if graph_text:
            user_message += f"\nKnowledge Graph Relations:\n{graph_text}\n"

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": settings.LLM_MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        "temperature": settings.LLM_TEMPERATURE
                    }
                )
                if res.status_code == 200:
                    answer = res.json()["choices"][0]["message"]["content"]
                    return {"answer": answer, "citations": citations}
                else:
                    logger.warning(f"OpenAI API error {res.status_code}: {res.text}. Falling back to local synthesis.")
        except Exception as e:
            logger.error(f"OpenAI connection error: {e}. Falling back to local synthesis.")

        return self._local_grounded_synthesis(query, context_chunks, graph_facts, citations)

    def _local_grounded_synthesis(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        graph_facts: Optional[List[str]],
        citations: List[Citation]
    ) -> Dict[str, Any]:
        """Synthesizes high-fidelity grounded answer directly from top ranked passages and graph facts."""
        top_passages = [c.content.strip() for c in context_chunks[:3]]
        
        # Build answer sentences grounded in retrieved passages
        paragraphs = []
        for i, passage in enumerate(top_passages, start=1):
            sentences = [s.strip() for s in passage.split(". ") if len(s.strip()) > 15]
            core_info = ". ".join(sentences[:2]) if sentences else passage
            paragraphs.append(f"{core_info} [{i}]")

        answer_body = " ".join(paragraphs)

        if graph_facts:
            facts_summary = " ".join([f"{f.rstrip('.')}." for f in graph_facts[:3]])
            answer_body += f"\n\n**Knowledge Graph Context**: {facts_summary}"

        return {
            "answer": answer_body,
            "citations": citations
        }

generator = GroundedGenerator()
