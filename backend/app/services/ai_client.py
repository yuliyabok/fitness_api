from __future__ import annotations

from dataclasses import dataclass

import httpx


class AIClientUnavailableError(RuntimeError):
    pass


class AIClientResponseError(RuntimeError):
    pass


@dataclass
class AIClientPrediction:
    fitness_index: float
    fatigue_risk: float
    trend: str
    recommendations: list[str]


class AIClient:
    def __init__(
        self,
        *,
        service_url: str,
        timeout: float = 30.0,
    ) -> None:
        normalized_url = service_url.strip().rstrip("/")
        if not normalized_url:
            raise AIClientUnavailableError("AI_SERVICE_URL is not configured")
        self._service_url = normalized_url
        self._timeout = timeout

    @property
    def predict_url(self) -> str:
        if self._service_url.endswith("/predict"):
            return self._service_url
        return f"{self._service_url}/predict"

    async def predict(self, payload: dict[str, object]) -> AIClientPrediction:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self.predict_url, json=payload)
        except httpx.HTTPError as exc:
            raise AIClientResponseError(f"AI service request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise AIClientResponseError(
                f"AI service returned HTTP {response.status_code}: {response.text.strip()}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AIClientResponseError("AI service returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise AIClientResponseError("AI service returned unexpected payload")

        raw_index = data.get("fitness_index")
        try:
            fitness_index = float(raw_index)
        except (TypeError, ValueError) as exc:
            raise AIClientResponseError("AI service returned invalid fitness_index") from exc

        raw_fatigue_risk = data.get("fatigue_risk")
        try:
            fatigue_risk = float(raw_fatigue_risk)
        except (TypeError, ValueError) as exc:
            raise AIClientResponseError("AI service returned invalid fatigue_risk") from exc

        trend = _normalize_trend(data.get("trend"))
        recommendations = _normalize_recommendations(data.get("recommendations"))
        return AIClientPrediction(
            fitness_index=fitness_index,
            fatigue_risk=fatigue_risk,
            trend=trend,
            recommendations=recommendations,
        )


def _normalize_recommendations(raw: object) -> list[str]:
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized:
            return [normalized]
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
        if items:
            return items
    raise AIClientResponseError("AI service returned empty recommendations")


def _normalize_trend(raw: object) -> str:
    if not isinstance(raw, str):
        raise AIClientResponseError("AI service returned invalid trend")
    normalized = raw.strip().lower()
    if normalized not in {"up", "stable", "down"}:
        raise AIClientResponseError("AI service returned invalid trend")
    return normalized
