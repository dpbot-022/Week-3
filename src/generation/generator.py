import time
import json
import re
import httpx
from typing import List, Dict, Any, Optional, Tuple, Generator
from src.core.config import settings
from src.core.logging import logger
from src.schemas.models import ScoredChunk, Citation
from src.generation.prompts import (
    SYSTEM_PROMPT_COMPLIANCE_ANALYST,
    STRICT_SYSTEM_PROMPT_RETRY,
    build_context_block
)
from src.guardrails.injection_guard import injection_guard
from src.guardrails.output_guard import output_guard

class GroundedGenerator:
    """Production grounded generator interacting with Ollama (qwen2.5:3b-instruct)
    with strict nonces, claim-level NLI verification, retry, and extractive mode fallback."""

    def __init__(self, ollama_url: str = settings.OLLAMA_BASE_URL, model_name: str = settings.OLLAMA_MODEL):
        self.ollama_url = ollama_url
        self.model_name = model_name

    def _call_ollama(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """Invokes Ollama generate API synchronously."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
            "stream": False,
            "options": {
                "temperature": min(temperature, 0.2),
                "top_p": 0.9,
                "num_predict": 1024
            }
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data.get("response", "").strip()

    def stream_ollama(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Generator[str, None, None]:
        """Streams Ollama generation tokens via HTTP chunked stream."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
            "stream": True,
            "options": {
                "temperature": min(temperature, 0.2),
                "top_p": 0.9,
                "num_predict": 1024
            }
        }
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Ollama returned HTTP {resp.status_code}")
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        yield chunk.get("response", "")

    def generate(
        self,
        query: str,
        context_chunks: List[ScoredChunk],
        accessible_doc_titles: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Executes full grounded generation pipeline:
        chunk scanning -> nonce context -> LLM generation -> citation validation -> NLI check -> retry/abstain."""
        start_time = time.time()

        # Step 1: Scan chunks for poisoning/prompt injection
        clean_chunks = injection_guard.scan_chunks(context_chunks)

        # Filter by calibrated relevance threshold
        relevant_chunks = [c for c in clean_chunks if c.final_score >= settings.RELEVANCE_THRESHOLD]

        # If no relevant chunks, abstain honestly immediately without fabricating
        if not relevant_chunks:
            suggestions = (accessible_doc_titles or [])[:3]
            sugg_text = f" Suggested topics: {', '.join(suggestions)}." if suggestions else ""
            return {
                "answer": f"I couldn't find this in the documents you have access to.{sugg_text}",
                "citations": [],
                "is_grounded": False,
                "generation_mode": "abstention",
                "faithfulness_score": 1.0,
                "model_name": self.model_name,
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            }

        # Build citations
        citations: List[Citation] = []
        for rank, c in enumerate(relevant_chunks, start=1):
            meta = c.metadata or {}
            snippet = c.content[:200] + "..." if len(c.content) > 200 else c.content
            citations.append(Citation(
                chunk_id=c.id,
                document_id=c.document_id,
                snippet=snippet,
                score=round(c.final_score, 4),
                rank=rank
            ))

        # Build nonce-delimited untrusted context
        nonce, start_boundary, end_boundary = injection_guard.generate_nonce_boundaries()
        formatted_chunks = "\n\n".join([
            f"[{i+1}] Title: {c.metadata.get('title', 'Policy')}, Page: {c.metadata.get('page_number', 1)}\n{c.content}"
            for i, c in enumerate(relevant_chunks)
        ])
        untrusted_context = build_context_block(nonce, formatted_chunks)
        user_message = f"User Question: {query}\n\n{untrusted_context}\n\nAnswer directly and concisely in 1 to 2 sentences using ONLY the provided passages, citing with [1]."

        # Generation with Ollama and Extractive Mode fallback
        generation_mode = "grounded"
        raw_answer = ""
        try:
            raw_answer = self._call_ollama(SYSTEM_PROMPT_COMPLIANCE_ANALYST, user_message)
        except Exception as e:
            logger.warning(f"Ollama call failed ({e}). Activating labeled Extractive mode.")
            generation_mode = "extractive"
            # Extractive mode: return top cited passages directly
            extracted_passages = [f"[{i+1}] {c.content}" for i, c in enumerate(relevant_chunks[:3])]
            raw_answer = "Extractive mode (LLM service unavailable):\n\n" + "\n\n".join(extracted_passages)

        # Step 2: Validate Citations
        valid_indices = set(range(1, len(citations) + 1))
        cited_indices = [int(m) for m in re.findall(r"\[(\d+)\]", raw_answer)]
        invalid_citations = [idx for idx in cited_indices if idx not in valid_indices]

        # If LLM omitted citation tag on grounded answer, append [1]
        if len(cited_indices) == 0 and len(citations) > 0 and generation_mode == "grounded":
            raw_answer = f"{raw_answer.rstrip('.')} [1]."
            cited_indices = [1]

        # Step 3: NLI Claim-level support check (for generated answers)
        faithfulness_score = 1.0
        is_supported = True
        if generation_mode == "grounded":
            chunk_texts = [c.content for c in relevant_chunks]
            faithfulness_score, unsupported = output_guard.check_faithfulness(raw_answer, chunk_texts)
            is_supported = (len(unsupported) == 0 and faithfulness_score >= 0.7)

            if not is_supported or len(invalid_citations) > 0:
                logger.info("First generation failed NLI support check or had invalid citations. Retrying once with stricter prompt.")
                try:
                    retry_answer = self._call_ollama(STRICT_SYSTEM_PROMPT_RETRY, user_message, temperature=0.1)
                    retry_score, retry_unsupported = output_guard.check_faithfulness(retry_answer, chunk_texts)
                    retry_supported = (len(retry_unsupported) == 0 and retry_score >= 0.7)
                    if retry_supported:
                        raw_answer = retry_answer
                        faithfulness_score = retry_score
                        is_supported = True
                    else:
                        logger.warning("Retry also failed NLI support check. Abstaining honestly.")
                        suggestions = (accessible_doc_titles or [])[:3]
                        sugg_text = f" Suggested topics: {', '.join(suggestions)}." if suggestions else ""
                        return {
                            "answer": f"I couldn't find this in the documents you have access to.{sugg_text}",
                            "citations": [],
                            "is_grounded": False,
                            "generation_mode": "abstention",
                            "faithfulness_score": 0.0,
                            "model_name": self.model_name,
                            "latency_ms": round((time.time() - start_time) * 1000, 2)
                        }
                except Exception as e:
                    logger.error(f"Retry generation failed: {e}")

        # Step 4: Output PII Scrub
        sanitized_answer, has_pii, pii_findings = output_guard.sanitize_output(raw_answer)

        latency = round((time.time() - start_time) * 1000, 2)
        return {
            "answer": sanitized_answer,
            "citations": citations,
            "is_grounded": True,
            "generation_mode": generation_mode,
            "faithfulness_score": faithfulness_score,
            "model_name": self.model_name,
            "latency_ms": latency
        }

grounded_generator = GroundedGenerator()
generator = grounded_generator  # Backward compatibility alias
