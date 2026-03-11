"""Configuration dataclass for LiteLLM Triage guardrail."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class TriageConfig:
    """Configuration for the Triage guardrail.

    Attributes:
        sensitive_model: Model to route sensitive requests to (e.g., "ollama/llama3")
        public_model: Model for non-sensitive requests (e.g., "gpt-4o")
        classifier: Classification strategy - "presidio", "local_llm", or "hybrid"
        threshold: Sensitivity threshold (0.0-1.0), above which content is routed locally
        presidio_url: URL of the Presidio Analyzer service
        ollama_url: URL of the Ollama service
        ollama_classifier_model: Model to use for local LLM classification
    """

    sensitive_model: str
    public_model: str
    classifier: Literal["presidio", "local_llm", "hybrid"] = "hybrid"
    threshold: float = 0.6
    presidio_url: str = "http://localhost:5002"
    ollama_url: str = "http://localhost:11434"
    ollama_classifier_model: str = "llama3.2:1b"

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be between 0.0 and 1.0, got {self.threshold}")
        if self.classifier not in ("presidio", "local_llm", "hybrid"):
            raise ValueError(
                f"classifier must be 'presidio', 'local_llm', or 'hybrid', got {self.classifier}"
            )
