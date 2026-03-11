"""Abstract base class for content classifiers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ClassifierResult:
    """Result from a content classifier.

    Attributes:
        is_sensitive: Whether the content was classified as sensitive
        score: Sensitivity score from 0.0 (not sensitive) to 1.0 (highly sensitive)
        stage: Which classifier stage produced this result
        entities: List of detected entity types (e.g., ["PERSON", "EMAIL_ADDRESS"])
        latency_ms: Time taken for classification in milliseconds
    """

    is_sensitive: bool
    score: float
    stage: Literal["presidio", "local_llm"]
    entities: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


class BaseClassifier(ABC):
    """Abstract base class for content classifiers."""

    @abstractmethod
    async def classify(self, text: str) -> ClassifierResult:
        """Classify text for sensitivity.

        Args:
            text: The text content to classify

        Returns:
            ClassifierResult with sensitivity determination
        """
        ...
