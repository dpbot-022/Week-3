import pytest
import respx
import httpx
from fastapi import HTTPException
from src.generation.generator import generator
from src.schemas.models import ScoredChunk

@pytest.fixture
def sample_chunks():
    return [
        ScoredChunk(
            id="c-001",
            document_id="doc-001",
            content="Reciprocal Rank Fusion (RRF) calculates score = sum(1 / (k + rank)) with k=60.",
            final_score=0.92,
            char_start=100,
            char_end=200
        )
    ]

# ---------------------------------------------------------------------------
# GEMINI PROVIDER TESTS
# ---------------------------------------------------------------------------
@respx.mock
def test_gemini_provider_success(sample_chunks):
    route = respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=test-gemini-key").mock(
        return_value=httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "RRF combines rankings using k=60 [1]."}]}}]
        })
    )
    result = generator.generate(
        query="What is RRF formula?",
        context_chunks=sample_chunks,
        provider="gemini",
        api_key="test-gemini-key"
    )
    assert route.called
    assert "RRF combines rankings" in result["answer"]
    assert len(result["citations"]) == 1

@respx.mock
def test_gemini_provider_auth_error_raises_503(sample_chunks):
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=invalid-key").mock(
        return_value=httpx.Response(401, text="API key not valid")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test query",
            context_chunks=sample_chunks,
            provider="gemini",
            api_key="invalid-key"
        )
    assert exc.value.status_code == 503
    assert "authentication failed" in exc.value.detail

@respx.mock
def test_gemini_provider_rate_limit_raises_503(sample_chunks):
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=test-gemini-key").mock(
        return_value=httpx.Response(429, text="Resource exhausted")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test query",
            context_chunks=sample_chunks,
            provider="gemini",
            api_key="test-gemini-key"
        )
    assert exc.value.status_code == 503
    assert "rate limit exceeded" in exc.value.detail

@respx.mock
def test_gemini_provider_timeout_raises_503(sample_chunks):
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=test-gemini-key").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test query",
            context_chunks=sample_chunks,
            provider="gemini",
            api_key="test-gemini-key"
        )
    assert exc.value.status_code == 503
    assert "timed out" in exc.value.detail

# ---------------------------------------------------------------------------
# OPENAI PROVIDER TESTS
# ---------------------------------------------------------------------------
@respx.mock
def test_openai_provider_success(sample_chunks):
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "OpenAI answer based on context [1]."}}]
        })
    )
    result = generator.generate(
        query="What is RRF?",
        context_chunks=sample_chunks,
        provider="openai",
        api_key="sk-test-key"
    )
    assert route.called
    assert "OpenAI answer" in result["answer"]

@respx.mock
def test_openai_provider_auth_error_raises_503(sample_chunks):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="Incorrect API key")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test",
            context_chunks=sample_chunks,
            provider="openai",
            api_key="sk-bad-key"
        )
    assert exc.value.status_code == 503
    assert "authentication failed" in exc.value.detail

@respx.mock
def test_openai_provider_rate_limit_raises_503(sample_chunks):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="Rate limit reached")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test",
            context_chunks=sample_chunks,
            provider="openai",
            api_key="sk-test-key"
        )
    assert exc.value.status_code == 503
    assert "rate limit exceeded" in exc.value.detail

# ---------------------------------------------------------------------------
# ANTHROPIC PROVIDER TESTS
# ---------------------------------------------------------------------------
@respx.mock
def test_anthropic_provider_success(sample_chunks):
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"text": "Anthropic grounded answer [1]."}]
        })
    )
    result = generator.generate(
        query="What is RRF?",
        context_chunks=sample_chunks,
        provider="anthropic",
        api_key="sk-ant-test"
    )
    assert route.called
    assert "Anthropic grounded answer" in result["answer"]

@respx.mock
def test_anthropic_provider_server_error_raises_503(sample_chunks):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    with pytest.raises(HTTPException) as exc:
        generator.generate(
            query="Test",
            context_chunks=sample_chunks,
            provider="anthropic",
            api_key="sk-ant-test"
        )
    assert exc.value.status_code == 503
    assert "returned error (500)" in exc.value.detail

# ---------------------------------------------------------------------------
# LOCAL SYNTHESIS TEST
# ---------------------------------------------------------------------------
def test_local_extractive_synthesis(sample_chunks):
    result = generator.generate(
        query="Explain RRF",
        context_chunks=sample_chunks,
        provider="synthesis"
    )
    assert "[1]" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["is_grounded"] is True
