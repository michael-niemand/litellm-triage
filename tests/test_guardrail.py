"""Tests for the TriageGuardrail."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from litellm_triage.classifier.base import ClassifierResult
from litellm_triage.guardrail import TriageGuardrail


class TestTriageGuardrail:
    """Tests for the TriageGuardrail plugin."""

    @pytest.fixture
    def guardrail(self):
        return TriageGuardrail(
            sensitive_model="ollama/llama3",
            public_model="gpt-4o",
            classifier="hybrid",
            threshold=0.6,
            presidio_url="http://localhost:5002",
            ollama_url="http://localhost:11434",
        )

    @pytest.mark.asyncio
    async def test_sensitive_prompt_reroutes(self, guardrail):
        """Test that sensitive prompts are routed to the sensitive model."""
        # Mock the _classify method to return sensitive
        guardrail._classify = AsyncMock(
            return_value=ClassifierResult(
                is_sensitive=True,
                score=0.9,
                stage="presidio",
                entities=["PERSON"],
                latency_ms=10.0,
            )
        )

        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "My SSN is 123-45-6789"}],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        assert result["model"] == "ollama/llama3"

    @pytest.mark.asyncio
    async def test_clean_prompt_unchanged(self, guardrail):
        """Test that clean prompts keep the original model."""
        # Mock the _classify method to return clean
        guardrail._classify = AsyncMock(
            return_value=ClassifierResult(
                is_sensitive=False,
                score=0.1,
                stage="presidio",
                entities=[],
                latency_ms=5.0,
            )
        )

        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "What is the weather?"}],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        # Model should remain unchanged
        assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_metadata_injected(self, guardrail):
        """Test that triage metadata is injected into the request."""
        guardrail._classify = AsyncMock(
            return_value=ClassifierResult(
                is_sensitive=True,
                score=0.85,
                stage="local_llm",
                entities=["health info"],
                latency_ms=150.0,
            )
        )

        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "I have diabetes"}],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        assert "metadata" in result
        assert "triage" in result["metadata"]
        triage = result["metadata"]["triage"]
        assert "score" in triage
        assert "decision" in triage
        assert "classifier_stage" in triage
        assert "latency_ms" in triage
        assert "total_latency_ms" in triage
        assert "entities" in triage
        assert triage["score"] == 0.85
        assert triage["decision"] == "local"
        assert triage["classifier_stage"] == "local_llm"

    @pytest.mark.asyncio
    async def test_empty_messages(self, guardrail):
        """Test that empty messages are handled gracefully."""
        data = {
            "model": "gpt-4o",
            "messages": [],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        # Should return data unchanged
        assert result["model"] == "gpt-4o"
        assert "metadata" not in result or "triage" not in result.get("metadata", {})

    @pytest.mark.asyncio
    async def test_whitespace_only_content(self, guardrail):
        """Test that whitespace-only content is handled gracefully."""
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "   \n\t   "}],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        # Should return data unchanged
        assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_extract_text_simple(self, guardrail):
        """Test text extraction from simple string content."""
        data = {
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello world"},
            ]
        }

        text = guardrail._extract_text(data)

        assert "You are helpful" in text
        assert "Hello world" in text

    @pytest.mark.asyncio
    async def test_extract_text_multimodal(self, guardrail):
        """Test text extraction from multimodal content blocks."""
        data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ]
        }

        text = guardrail._extract_text(data)

        assert "What is in this image?" in text

    @pytest.mark.asyncio
    async def test_existing_metadata_preserved(self, guardrail):
        """Test that existing metadata is preserved when adding triage info."""
        guardrail._classify = AsyncMock(
            return_value=ClassifierResult(
                is_sensitive=False,
                score=0.1,
                stage="presidio",
                entities=[],
                latency_ms=5.0,
            )
        )

        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "metadata": {"user_id": "123", "session_id": "abc"},
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        assert result["metadata"]["user_id"] == "123"
        assert result["metadata"]["session_id"] == "abc"
        assert "triage" in result["metadata"]


class TestTriageGuardrailIntegration:
    """Integration tests with mocked HTTP endpoints."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_full_sensitive_flow(self):
        """Test full flow with actual HTTP mocking."""
        respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(
                200,
                json=[
                    {"entity_type": "CREDIT_CARD", "score": 0.95, "start": 0, "end": 16}
                ],
            )
        )

        guardrail = TriageGuardrail(
            sensitive_model="ollama/llama3",
            public_model="gpt-4o",
            classifier="presidio",
            threshold=0.6,
            presidio_url="http://localhost:5002",
            ollama_url="http://localhost:11434",
        )

        data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "My credit card is 4111-1111-1111-1111"}
            ],
        }

        result = await guardrail.async_pre_call_hook(data, None, "completion")

        assert result["model"] == "ollama/llama3"
        assert result["metadata"]["triage"]["decision"] == "local"
        assert "CREDIT_CARD" in result["metadata"]["triage"]["entities"]
