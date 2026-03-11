"""Local LLM-based semantic classifier (Stage 2)."""

import json
import re
import time
from typing import Any

import httpx

from litellm_triage.classifier.base import BaseClassifier, ClassifierResult

CLASSIFIER_PROMPT = """You are a privacy classifier. Analyze the following text and determine if it contains sensitive information that should NOT be sent to a cloud AI provider.

Sensitive includes: personal health info, financial details, credentials/passwords, confidential business strategy, legal matters, personal relationships/family issues, location data, private communications.

Text: {text}

Respond with JSON only: {{"sensitive": true/false, "reason": "brief reason", "score": 0.0-1.0}}"""


class LocalLLMClassifier(BaseClassifier):
    """Semantic classification using a local LLM via Ollama.

    This is Stage 2 of the hybrid classifier. It uses a small, fast local
    model to perform semantic analysis of content that passed Stage 1
    (Presidio) without detection.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3.2:1b",
        threshold: float = 0.6,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the local LLM classifier.

        Args:
            ollama_url: URL of the Ollama service
            model: Model to use for classification
            threshold: Score threshold above which content is considered sensitive
            timeout: HTTP request timeout in seconds
        """
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.threshold = threshold
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    def _parse_response(self, content: str) -> tuple[bool, float, str]:
        """Parse the LLM response to extract classification.

        Args:
            content: Raw response content from the LLM

        Returns:
            Tuple of (is_sensitive, score, reason)
        """
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if not json_match:
            return False, 0.0, "Failed to parse response"

        try:
            data = json.loads(json_match.group())
            sensitive = bool(data.get("sensitive", False))
            score = float(data.get("score", 0.5 if sensitive else 0.0))
            reason = str(data.get("reason", ""))
            return sensitive, score, reason
        except (json.JSONDecodeError, ValueError, TypeError):
            return False, 0.0, "Failed to parse response"

    async def classify(self, text: str) -> ClassifierResult:
        """Classify text using a local LLM.

        Calls Ollama's OpenAI-compatible chat completions endpoint
        with a privacy classification prompt.

        Args:
            text: The text content to analyze

        Returns:
            ClassifierResult with semantic classification results
        """
        start_time = time.perf_counter()

        client = await self._get_client()
        prompt = CLASSIFIER_PROMPT.format(text=text)

        try:
            response = await client.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 150,
                },
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
        except httpx.HTTPError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ClassifierResult(
                is_sensitive=False,
                score=0.0,
                stage="local_llm",
                entities=[],
                latency_ms=latency_ms,
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return ClassifierResult(
                is_sensitive=False,
                score=0.0,
                stage="local_llm",
                entities=[],
                latency_ms=latency_ms,
            )

        sensitive, score, reason = self._parse_response(content)

        entities = []
        if reason:
            entities = [reason]

        return ClassifierResult(
            is_sensitive=score >= self.threshold,
            score=score,
            stage="local_llm",
            entities=entities,
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
