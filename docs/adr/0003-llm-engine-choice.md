# ADR 0003: LLM Engine Choice - Local Ollama (Qwen2.5-3B-Instruct)

## Status
Accepted

## Context
SafeStrata is an internal regulatory compliance desk for a regulated financial institution.
Key non-negotiable requirements:
1. **Zero External Data Egress**: Sensitive banking policies, internal audit memos, and customer KYC inquiries must not leave the perimeter.
2. **Deterministic Grounding**: The LLM must generate answers strictly derived from provided context passages, never answering from general knowledge.
3. **Hardware Budget**: Deployable on standard 16 GB RAM enterprise workstations without dedicated data center GPUs.

## Decision
We select **Ollama** running **`qwen2.5:3b-instruct`** locally:
- **Low Memory & Fast Latency**: The 3B parameter model runs with full 4-bit/8-bit quantization consuming ~2.2 GB VRAM/RAM, delivering token throughput exceeding 45 tokens/second.
- **Strict Temperature**: Invoked with `temperature <= 0.2` and greedy top-p sampling.
- **Untrusted Context Delimiters**: Context chunks are wrapped with per-request cryptographically random hex nonces (`<UNTRUSTED_CONTEXT_nonce>`).
- **No Silent Fallbacks**: If Ollama becomes unreachable, the platform explicitly returns an HTTP 503 or an explicitly labeled "Extractive mode" (top ranked cited passages, zero fabrication).

## Consequences
- **Positive**: 100% private, zero egress, fast startup, highly compliant with bank air-gapped guidelines.
- **Negative**: Model size limits reasoning on 10+ hop queries; compensated by cross-encoder reranking and claim-level NLI verification.
