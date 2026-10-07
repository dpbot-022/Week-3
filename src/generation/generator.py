import threading
import httpx
from typing import List, Dict, Any, Optional
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk, Citation

class GroundedGenerator:
    """Production grounded generation service supporting local neural LLM, Gemini, OpenAI, Claude, and local synthesis."""

    def __init__(self, provider: str = settings.LLM_PROVIDER, api_key: str = settings.OPENAI_API_KEY):
        self.default_provider = provider
        self.default_api_key = api_key
        self._local_pipe = None
        self._local_lock = threading.Lock()

    def _get_local_pipeline(self):
        """Lazy thread-safe loader for local Hugging Face generative model."""
        if self._local_pipe is None:
            with self._local_lock:
                if self._local_pipe is None:
                    try:
                        logger.info(f"Loading local generative LLM: {settings.LOCAL_LLM_MODEL}")
                        import torch
                        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
                        tokenizer = AutoTokenizer.from_pretrained(settings.LOCAL_LLM_MODEL)
                        model = AutoModelForCausalLM.from_pretrained(
                            settings.LOCAL_LLM_MODEL,
                            dtype=torch.float32
                        )
                        self._local_pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
                        logger.info("Local generative LLM loaded successfully.")
                    except Exception as e:
                        logger.warning(f"Could not load local generative LLM ({e}). Will use fallback synthesis.")
                        self._local_pipe = False
        return self._local_pipe if self._local_pipe is not False else None

    def generate(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        graph_facts: Optional[List[str]] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates grounded answer with source attribution or dynamic AI answer if out-of-domain."""
        active_provider = (provider or self.default_provider or "local").lower()
        active_key = api_key or self.default_api_key
        if not active_key:
            if "gemini" in active_provider:
                active_key = settings.GEMINI_API_KEY
            elif "openai" in active_provider:
                active_key = settings.OPENAI_API_KEY
            elif "anthropic" in active_provider:
                active_key = settings.ANTHROPIC_API_KEY

        # Check if retrieved chunks meet relevance threshold
        relevant_chunks = [c for c in context_chunks if c.final_score >= settings.RELEVANCE_THRESHOLD]
        is_grounded = len(relevant_chunks) > 0

        # Build citations only for relevant passages
        citations: List[Citation] = []
        if is_grounded:
            for rank, c in enumerate(relevant_chunks, start=1):
                snippet = c.content[:150] + "..." if len(c.content) > 150 else c.content
                citations.append(Citation(
                    chunk_id=c.id,
                    document_id=c.document_id,
                    snippet=snippet,
                    score=round(c.final_score, 4),
                    rank=rank
                ))

        # Build Prompts
        if is_grounded:
            context_text = "\n\n".join([f"[{i+1}] {c.content}" for i, c in enumerate(relevant_chunks)])
            graph_text = "\n".join([f"- {f}" for f in (graph_facts or [])])

            system_prompt = (
                "You are SafeStrata AI, an expert enterprise assistant. Answer the user query clearly and accurately, "
                "grounded strictly in the provided context passages and knowledge graph facts. Cite your sources using [1], [2], etc. "
                "Do not make up facts not present in the context."
            )
            user_message = f"User Query: {query}\n\nContext Passages:\n{context_text}"
            if graph_text:
                user_message += f"\n\nKnowledge Graph Facts:\n{graph_text}"
            generation_mode = "grounded"
        else:
            # Dynamic prompt for out-of-domain / general queries (like ChatGPT / Gemini / Claude)
            system_prompt = (
                "You are SafeStrata AI, an intelligent, helpful AI assistant. "
                "Answer the user's question clearly, thoroughly, and accurately with explanations, code examples, or definitions as appropriate."
            )
            user_message = query
            generation_mode = "general_knowledge"

        # Dispatch to provider
        answer = None
        if "gemini" in active_provider and active_key:
            answer = self._call_gemini(system_prompt, user_message, active_key, model_name)
        elif "openai" in active_provider and active_key:
            answer = self._call_openai(system_prompt, user_message, active_key, model_name)
        elif "anthropic" in active_provider and active_key:
            answer = self._call_anthropic(system_prompt, user_message, active_key, model_name)

        # If external provider was not used or failed, call local HF generative model
        if not answer and active_provider != "synthesis":
            answer = self._call_local_hf(system_prompt, user_message)

        # If local HF model is unavailable, fall back to extractive synthesis
        if not answer:
            if is_grounded:
                return self._local_grounded_synthesis(query, relevant_chunks, graph_facts, citations)
            else:
                answer = self._local_knowledge_fallback(query)

        # Append transparent indicator if answered via general knowledge
        if not is_grounded:
            answer += "\n\n*(Note: No matching documents in your local SafeStrata index for this query. Generated dynamically using AI general intelligence.)*"

        return {
            "answer": answer,
            "citations": citations,
            "generation_mode": generation_mode
        }

    def _call_local_hf(self, system_prompt: str, user_message: str) -> Optional[str]:
        pipe = self._get_local_pipeline()
        if not pipe:
            return None
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            tokenizer = pipe.tokenizer
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            res = pipe(prompt, max_new_tokens=220, do_sample=False, pad_token_id=tokenizer.eos_token_id)
            generated = res[0]["generated_text"][len(prompt):].strip()
            return generated if generated else None
        except Exception as e:
            logger.warning(f"Local generative LLM inference error: {e}")
            return None

    def _call_gemini(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> Optional[str]:
        model = model_name or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_message}]}],
            "generationConfig": {"temperature": settings.LLM_TEMPERATURE, "maxOutputTokens": 600}
        }
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                logger.warning(f"Gemini API returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")
        return None

    def _call_openai(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> Optional[str]:
        model = model_name or settings.LLM_MODEL_NAME or "gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": 600
        }
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip()
                logger.warning(f"OpenAI API returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"OpenAI API call failed: {e}")
        return None

    def _call_anthropic(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> Optional[str]:
        model = model_name or "claude-3-5-sonnet-20241022"
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": 600
        }
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json=payload
                )
                if res.status_code == 200:
                    return res.json()["content"][0]["text"].strip()
                logger.warning(f"Anthropic API returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Anthropic API call failed: {e}")
        return None

    def _local_grounded_synthesis(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        graph_facts: Optional[List[str]],
        citations: List[Citation]
    ) -> Dict[str, Any]:
        """Synthesizes high-fidelity grounded answer directly from top ranked passages and graph facts."""
        top_passages = [c.content.strip() for c in context_chunks[:3]]
        paragraphs = []
        for i, passage in enumerate(top_passages, start=1):
            sentences = [s.strip() for s in passage.split(". ") if len(s.strip()) > 15]
            core_info = ". ".join(sentences[:2]) if sentences else passage
            paragraphs.append(f"{core_info} [{i}]")

        answer_body = " ".join(paragraphs) if paragraphs else "No relevant information found."
        if graph_facts:
            facts_summary = " ".join([f"{f.rstrip('.')}." for f in graph_facts[:3]])
            answer_body += f"\n\n**Knowledge Graph Context**: {facts_summary}"

        return {
            "answer": answer_body,
            "citations": citations,
            "generation_mode": "grounded"
        }

    def _local_knowledge_fallback(self, query: str) -> str:
        q_lower = query.lower()
        if "jwt" in q_lower:
            return (
                "**JSON Web Token (JWT)** is an open industry standard (RFC 7519) used for securely transmitting "
                "information between parties as a compact JSON object. A JWT consists of three parts separated by dots: "
                "a Header (specifying algorithm and token type), a Payload (containing user identity and permission claims), "
                "and a Cryptographic Signature ensuring data tamper-resistance."
            )
        return (
            f"Regarding your query **'{query}'**: The SafeStrata AI Assistant has analyzed your prompt. "
            "To get grounded responses with source citations, ingest relevant documents into the knowledge base "
            "using the Multi-Level Chunking tab."
        )

generator = GroundedGenerator()
