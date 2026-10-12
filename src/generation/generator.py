import threading
import httpx
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk, Citation

class GroundedGenerator:
    """Production grounded generation service supporting local neural LLM, Gemini, OpenAI, Claude, and extractive synthesis."""

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
                        logger.warning(f"Could not load local generative LLM ({e}). Will use extractive synthesis.")
                        self._local_pipe = False
        return self._local_pipe if self._local_pipe is not False else None

    def generate(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates grounded answer with source attribution. Never falls back to ungrounded general knowledge."""
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
        if not relevant_chunks:
            return {
                "answer": "Abstained: Insufficient grounded context retrieved to answer this query safely.",
                "citations": [],
                "is_grounded": False
            }

        # Build citations for relevant passages
        citations: List[Citation] = []
        for rank, c in enumerate(relevant_chunks, start=1):
            snippet = c.content[:150] + "..." if len(c.content) > 150 else c.content
            citations.append(Citation(
                chunk_id=c.id,
                document_id=c.document_id,
                snippet=snippet,
                score=round(c.final_score, 4),
                rank=rank,
                char_start=c.char_start,
                char_end=c.char_end
            ))

        # Build Grounded Prompt
        context_text = "\n\n".join([f"[{i+1}] {c.content}" for i, c in enumerate(relevant_chunks)])
        system_prompt = (
            "You are SafeStrata AI, an expert enterprise assistant. Answer the user query clearly and accurately, "
            "grounded strictly in the provided context passages. Cite your sources using [1], [2], etc. "
            "Do not make up facts not present in the context. If the context does not contain enough information, "
            "explicitly state that the information is unavailable."
        )
        user_message = f"User Query: {query}\n\nContext Passages:\n{context_text}"

        answer = None
        if "gemini" in active_provider:
            answer = self._call_gemini(system_prompt, user_message, active_key, model_name)
        elif "openai" in active_provider:
            answer = self._call_openai(system_prompt, user_message, active_key, model_name)
        elif "anthropic" in active_provider:
            answer = self._call_anthropic(system_prompt, user_message, active_key, model_name)
        elif "local" in active_provider:
            answer = self._call_local_hf(system_prompt, user_message)

        # Fallback to local extractive grounded synthesis
        if not answer:
            return self._local_grounded_synthesis(query, relevant_chunks, citations)

        return {
            "answer": answer,
            "citations": citations,
            "is_grounded": True
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

    def _call_gemini(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> str:
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini API key not configured")
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
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Empty response from Gemini")
                elif res.status_code in (401, 403):
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Gemini authentication failed ({res.status_code})")
                elif res.status_code == 429:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini rate limit exceeded (429)")
                else:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Gemini API returned error ({res.status_code}): {res.text}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini API request timed out")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Gemini API error: {e}")

    def _call_openai(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> str:
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OpenAI API key not configured")
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
                elif res.status_code in (401, 403):
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"OpenAI authentication failed ({res.status_code})")
                elif res.status_code == 429:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OpenAI rate limit exceeded (429)")
                else:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"OpenAI API returned error ({res.status_code}): {res.text}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OpenAI API request timed out")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"OpenAI API error: {e}")

    def _call_anthropic(self, system_prompt: str, user_message: str, api_key: str, model_name: Optional[str]) -> str:
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Anthropic API key not configured")
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
                elif res.status_code in (401, 403):
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Anthropic authentication failed ({res.status_code})")
                elif res.status_code == 429:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Anthropic rate limit exceeded (429)")
                else:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Anthropic API returned error ({res.status_code}): {res.text}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Anthropic API request timed out")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Anthropic API error: {e}")

    def _local_grounded_synthesis(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        citations: List[Citation]
    ) -> Dict[str, Any]:
        """Synthesizes high-fidelity grounded answer directly from top ranked passages with explicit citations."""
        top_passages = [c.content.strip() for c in context_chunks[:3]]
        paragraphs = []
        for i, passage in enumerate(top_passages, start=1):
            sentences = [s.strip() for s in passage.split(". ") if len(s.strip()) > 15]
            core_info = ". ".join(sentences[:2]) if sentences else passage
            paragraphs.append(f"{core_info} [{i}]")

        answer_body = " ".join(paragraphs) if paragraphs else "No relevant information found."

        return {
            "answer": answer_body,
            "citations": citations,
            "is_grounded": True
        }

generator = GroundedGenerator()
