"""Jev (TypeSafe AI) adapter for the Classifier port.

Asks one Choice question: which of the board's categories fits this task.
Any failure becomes ClassifierUnavailable; the key never appears in errors.
"""

from collections.abc import Sequence

from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

from season.application.ports import ClassifierUnavailable, Prediction
from season.domain.model import Category

INSTRUCTIONS = (
    "This is one item on a personal weekly to-do list. Which category does "
    "it belong to? Choose the category that best fits the work the item "
    "describes, using the descriptions of the categories."
)


class JevClassifier:
    def __init__(self, api_key: str, model: str = "jev-latest", timeout: float = 8.0,
                 context: str | None = None, client: TypeSafeClient | None = None) -> None:
        self._client = client or TypeSafeClient(
            api_key=api_key, model=model, timeout=timeout,
            retry=RetryPolicy(max_retries=1, timeout=timeout * 2),
        )
        # Optional extra context (SEASON_CONTEXT in .env), e.g. "master's student in Tokyo,
        # finishing a thesis, preparing for job interviews in Germany". Kept out of the repo.
        self._instructions = f"{context.strip()} {INSTRUCTIONS}" if context and context.strip() else INSTRUCTIONS

    def predict(self, text: str, categories: Sequence[Category]) -> Prediction:
        if not categories:
            raise ClassifierUnavailable("no categories to choose from")
        question = Choice(instructions=self._instructions,
                          criteria={c.key: f"{c.label}: {c.description}" for c in categories})
        try:
            response = self._client.system_one(state={"task": text}, questions={"category": question})
            answer = response.answers["category"]
            choice = answer.choice
            return Prediction(category=choice,
                              probability=float(answer.probabilities.get(choice, 0.0)),
                              confidence=float(answer.confidence))
        except Exception as exc:  # adapter boundary: any SDK/network failure
            raise ClassifierUnavailable(type(exc).__name__) from None


class UnavailableClassifier:
    """Used when no API key is configured. Everything falls back to OTHER."""

    def predict(self, text: str, categories: Sequence[Category]) -> Prediction:
        raise ClassifierUnavailable("TYPESAFE_API_KEY is not set")
