"""Tests for the classifier implementations."""

import json

import pytest
import respx
from httpx import Response

from litellm_triage.classifier.local_llm import LocalLLMClassifier
from litellm_triage.classifier.presidio import PresidioClassifier


class TestPresidioClassifier:
    """Tests for the Presidio classifier."""

    @pytest.fixture
    def classifier(self):
        return PresidioClassifier(
            presidio_url="http://localhost:5002", threshold=0.6
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_presidio_sensitive(self, classifier):
        """Test that high-scoring entities are flagged as sensitive."""
        respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(
                200,
                json=[
                    {"entity_type": "PERSON", "score": 0.9, "start": 0, "end": 8}
                ],
            )
        )

        result = await classifier.classify("John Doe is here")

        assert result.is_sensitive is True
        assert result.score == 0.9
        assert result.stage == "presidio"
        assert "PERSON" in result.entities

    @respx.mock
    @pytest.mark.asyncio
    async def test_presidio_clean(self, classifier):
        """Test that empty results are classified as not sensitive."""
        respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(200, json=[])
        )

        result = await classifier.classify("What is the weather today?")

        assert result.is_sensitive is False
        assert result.score == 0.0
        assert result.stage == "presidio"
        assert result.entities == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_presidio_unavailable(self, classifier):
        """Test fail-open behavior when Presidio is unavailable."""
        respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        result = await classifier.classify("My SSN is 123-45-6789")

        # Should fail open - treat as not sensitive
        assert result.is_sensitive is False
        assert result.score == 0.0
        assert result.stage == "presidio"

    @respx.mock
    @pytest.mark.asyncio
    async def test_presidio_below_threshold(self, classifier):
        """Test that low-scoring entities are not flagged."""
        respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(
                200,
                json=[
                    {"entity_type": "PERSON", "score": 0.3, "start": 0, "end": 8}
                ],
            )
        )

        result = await classifier.classify("Maybe John")

        assert result.is_sensitive is False
        assert result.score == 0.3
        assert result.stage == "presidio"


class TestLocalLLMClassifier:
    """Tests for the local LLM classifier."""

    @pytest.fixture
    def classifier(self):
        return LocalLLMClassifier(
            ollama_url="http://localhost:11434",
            model="llama3.2:1b",
            threshold=0.6,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_local_llm_sensitive(self, classifier):
        """Test that sensitive content is detected."""
        respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "sensitive": True,
                                        "score": 0.85,
                                        "reason": "health info",
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )

        result = await classifier.classify("I have diabetes and take insulin")

        assert result.is_sensitive is True
        assert result.score == 0.85
        assert result.stage == "local_llm"

    @respx.mock
    @pytest.mark.asyncio
    async def test_local_llm_clean(self, classifier):
        """Test that clean content is not flagged."""
        respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "sensitive": False,
                                        "score": 0.1,
                                        "reason": "general question",
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )

        result = await classifier.classify("What is 2 + 2?")

        assert result.is_sensitive is False
        assert result.score == 0.1
        assert result.stage == "local_llm"

    @respx.mock
    @pytest.mark.asyncio
    async def test_local_llm_unavailable(self, classifier):
        """Test fail-open behavior when Ollama is unavailable."""
        respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=Response(500, text="Service Unavailable")
        )

        result = await classifier.classify("My bank account is 12345")

        # Should fail open
        assert result.is_sensitive is False
        assert result.score == 0.0
        assert result.stage == "local_llm"


class TestHybridClassifier:
    """Tests for the hybrid classification strategy."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_hybrid_fast_path(self):
        """Test that Presidio detection shortcuts local LLM call."""
        from litellm_triage.guardrail import TriageGuardrail

        # Mock Presidio to return sensitive
        presidio_route = respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(
                200,
                json=[
                    {"entity_type": "PERSON", "score": 0.9, "start": 0, "end": 8}
                ],
            )
        )

        # Mock local LLM (should NOT be called)
        llm_route = respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"sensitive": False, "score": 0.1, "reason": "clean"}
                                )
                            }
                        }
                    ]
                },
            )
        )

        guardrail = TriageGuardrail(
            sensitive_model="ollama/llama3",
            public_model="gpt-4o",
            classifier="hybrid",
            threshold=0.6,
            presidio_url="http://localhost:5002",
            ollama_url="http://localhost:11434",
        )

        result = await guardrail._classify("John Doe's information")

        assert result.is_sensitive is True
        assert result.stage == "presidio"
        assert presidio_route.called
        assert not llm_route.called  # Local LLM should NOT have been called

    @respx.mock
    @pytest.mark.asyncio
    async def test_hybrid_escalation(self):
        """Test that Presidio miss escalates to local LLM."""
        from litellm_triage.guardrail import TriageGuardrail

        # Mock Presidio to return clean (low score)
        presidio_route = respx.post("http://localhost:5002/analyze").mock(
            return_value=Response(
                200,
                json=[
                    {"entity_type": "PERSON", "score": 0.2, "start": 0, "end": 5}
                ],
            )
        )

        # Mock local LLM to return sensitive
        llm_route = respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "sensitive": True,
                                        "score": 0.9,
                                        "reason": "confidential strategy",
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )

        guardrail = TriageGuardrail(
            sensitive_model="ollama/llama3",
            public_model="gpt-4o",
            classifier="hybrid",
            threshold=0.6,
            presidio_url="http://localhost:5002",
            ollama_url="http://localhost:11434",
        )

        result = await guardrail._classify(
            "Our Q4 strategy is to acquire competitor X"
        )

        assert result.is_sensitive is True
        assert result.stage == "local_llm"
        assert presidio_route.called
        assert llm_route.called  # Local LLM should have been called
