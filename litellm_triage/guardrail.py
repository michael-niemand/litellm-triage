"""Main TriageGuardrail plugin for LiteLLM."""

import time
from typing import Any, Dict, Optional

from litellm.integrations.custom_guardrail import CustomGuardrail

from .classifier.base import ClassifierResult
from .classifier.local_llm import LocalLLMClassifier
from .classifier.presidio import PresidioClassifier
from .config import TriageConfig


class TriageGuardrail(CustomGuardrail):
    """Content-aware privacy routing guardrail for LiteLLM.

    Routes requests to local or cloud models based on content sensitivity
    using a hybrid classification approach (Presidio + local LLM).

    IMPORTANT — sensitive_model / public_model must be provider model strings
    (e.g. "anthropic/claude-haiku-4-5-20251001", "ollama/llama3"), NOT
    LiteLLM router group names. The hook fires inside litellm.acompletion()
    after the router has already resolved group names to deployments.
    """

    def __init__(
        self,
        sensitive_model: str,
        public_model: str,
        classifier: str = "hybrid",
        threshold: float = 0.85,
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
            # Presidio not sure — escalate to local LLM
            return await self._local_llm.classify(text)

    async def async_pre_call_deployment_hook(
        self, kwargs: Dict[str, Any], call_type: Optional[Any] = None
    ) -> Optional[dict]:
        """Override to work around a LiteLLM bug where default_on is ignored.

        LiteLLM's base implementation bails early if 'guardrails' is absent from
        the request kwargs — before it ever checks self.default_on. This override
        skips that early-return when default_on=True so the guardrail fires on
        all requests as intended.

        Upstream issue: https://github.com/BerriAI/litellm/issues (TODO: file)
        """
        from litellm.caching.caching import DualCache
        from litellm.integrations.custom_guardrail import GuardrailEventHooks
        from litellm.proxy._types import UserAPIKeyAuth
        from litellm.types.utils import CallTypes

        # Only skip the guard when default_on is active; otherwise honour it
        if not self.default_on:
            litellm_guardrails = kwargs.get("guardrails")
            if litellm_guardrails is None or not isinstance(litellm_guardrails, list):
                return kwargs

        if (
            self.should_run_guardrail(
                data=kwargs, event_type=GuardrailEventHooks.pre_call
            )
            is not True
        ):
            return kwargs

        if call_type in (CallTypes.completion, CallTypes.acompletion):
            result = await self.async_pre_call_hook(
                user_api_key_dict=UserAPIKeyAuth(
                    user_id=kwargs.get("user_api_key_user_id"),
                    team_id=kwargs.get("user_api_key_team_id"),
                    end_user_id=kwargs.get("user_api_key_end_user_id"),
                    api_key=kwargs.get("user_api_key_hash"),
                    request_route=kwargs.get("user_api_key_request_route"),
                ),
                cache=DualCache(),
                data=kwargs,
                call_type=call_type,
            )
            if result is not None:
                return result

        return kwargs

    async def async_pre_call_hook(
        self,
        data: dict,
        cache: Any,
        call_type: Any,
        **kwargs,
    ) -> dict:
        """Classify the prompt and reroute to local or cloud model accordingly."""
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

        # Inject triage metadata — rides LiteLLM's built-in OTel/Langfuse pipeline
        data.setdefault("metadata", {})["triage"] = {
            "score": round(result.score, 3),
            "decision": decision,
            "classifier_stage": result.stage,
            "entities": result.entities,
            "latency_ms": round(result.latency_ms, 1),
            "total_latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }

        return data
