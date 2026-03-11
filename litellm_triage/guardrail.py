"""Main TriageGuardrail plugin for LiteLLM."""

import time

from litellm.integrations.custom_guardrail import CustomGuardrail

from .classifier.base import ClassifierResult
from .classifier.local_llm import LocalLLMClassifier
from .classifier.presidio import PresidioClassifier
from .config import TriageConfig


class TriageGuardrail(CustomGuardrail):
    """Content-aware privacy routing guardrail for LiteLLM.

    Routes requests to local or cloud models based on content sensitivity
    using a hybrid classification approach (Presidio + local LLM).
    """

    def __init__(
        self,
        sensitive_model: str,
        public_model: str,
        classifier: str = "hybrid",
        threshold: float = 0.6,
        presidio_url: str = "http://localhost:5002",
        ollama_url: str = "http://localhost:11434",
        ollama_classifier_model: str = "llama3.2:1b",
        **kwargs,
    ):
        self.config = TriageConfig(
            sensitive_model=sensitive_model,
            public_model=public_model,
            classifier=classifier,
            threshold=threshold,
            presidio_url=presidio_url,
            ollama_url=ollama_url,
            ollama_classifier_model=ollama_classifier_model,
        )
        self._presidio = PresidioClassifier(
            presidio_url=presidio_url, threshold=threshold
        )
        self._local_llm = LocalLLMClassifier(
            ollama_url=ollama_url,
            model=ollama_classifier_model,
            threshold=threshold,
        )
        super().__init__(**kwargs)

    def _extract_text(self, data: dict) -> str:
        """Extract plain text from messages list."""
        messages = data.get("messages", [])
        parts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
        return " ".join(parts)

    async def _classify(self, text: str) -> ClassifierResult:
        """Classify text using configured strategy."""
        if self.config.classifier == "presidio":
            return await self._presidio.classify(text)
        elif self.config.classifier == "local_llm":
            return await self._local_llm.classify(text)
        else:  # hybrid
            result = await self._presidio.classify(text)
            if result.is_sensitive:
                return result  # fast path: Presidio caught it
            # Presidio not sure - escalate to local LLM
            return await self._local_llm.classify(text)

    async def async_pre_call_hook(
        self, data: dict, cache, call_type: str, **kwargs
    ) -> dict:
        """Pre-call hook to classify and route requests."""
        t0 = time.monotonic()

        text = self._extract_text(data)
        if not text.strip():
            return data

        result = await self._classify(text)

        # Routing decision
        if result.is_sensitive:
            data["model"] = self.config.sensitive_model
            decision = "local"
        else:
            decision = "cloud"

        # Inject triage metadata for observability (rides LiteLLM's OTel/Langfuse)
        data.setdefault("metadata", {})["triage"] = {
            "score": round(result.score, 3),
            "decision": decision,
            "classifier_stage": result.stage,
            "entities": result.entities,
            "latency_ms": round(result.latency_ms, 1),
            "total_latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }

        return data
