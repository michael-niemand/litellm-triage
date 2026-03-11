"""Presidio-based PII detection classifier (Stage 1)."""

import time
from typing import Any

import httpx

from litellm_triage.classifier.base import BaseClassifier, ClassifierResult


class PresidioClassifier(BaseClassifier):
    """Fast PII detection using Microsoft Presidio Analyzer.

    This is Stage 1 of the hybrid classifier. It performs fast regex and
    NLP-based detection of common PII entities like names, emails, phone
    numbers, SSNs, credit cards, etc.
    """

    def __init__(
        self,
        presidio_url: str = "http://localhost:5002",
        threshold: float = 0.6,
        timeout: float = 5.0,
    ) -> None:
        """Initialize the Presidio classifier.

        Args:
            presidio_url: URL of the Presidio Analyzer service
            threshold: Score threshold above which content is considered sensitive
            timeout: HTTP request timeout in seconds
        """
        self.presidio_url = presidio_url.rstrip("/")
        self.threshold = threshold
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def classify(self, text: str) -> ClassifierResult:
        """Classify text using Presidio Analyzer.

        Posts text to Presidio's /analyze endpoint and aggregates results.
        Returns the maximum confidence score across all detected entities.

        Args:
            text: The text content to analyze

        Returns:
            ClassifierResult with PII detection results
        """
        start_time = time.perf_counter()

        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.presidio_url}/analyze",
                json={
                    "text": text,
                    "language": "en",
                },
            )
            response.raise_for_status()
            results: list[dict[str, Any]] = response.json()
        except httpx.HTTPError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ClassifierResult(
                is_sensitive=False,
                score=0.0,
                stage="presidio",
                entities=[],
                latency_ms=latency_ms,
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if not results:
            return ClassifierResult(
                is_sensitive=False,
                score=0.0,
                stage="presidio",
                entities=[],
                latency_ms=latency_ms,
            )

        max_score = max(r.get("score", 0.0) for r in results)
        entities = list({r.get("entity_type", "UNKNOWN") for r in results})

        return ClassifierResult(
            is_sensitive=max_score >= self.threshold,
            score=max_score,
            stage="presidio",
            entities=entities,
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
