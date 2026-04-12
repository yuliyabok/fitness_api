from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ml_service.config import MLServiceSettings
from ml_service.schemas import PredictionRequest, PredictionResponse
from ml_service.services.inference import run_prediction_pipeline
from ml_service.services.model_loader import ModelArtifacts, ModelLoadingError, load_model_artifacts
from ml_service.services.preprocessing import prepare_inference_input
from ml_service.services.recommendation_engine import build_recommendations

logger = logging.getLogger(__name__)


def create_app(
    settings: MLServiceSettings | None = None,
    *,
    model_artifacts: ModelArtifacts | None = None,
) -> FastAPI:
    resolved_settings = settings or MLServiceSettings()
    _configure_logging(resolved_settings.log_level)

    app = FastAPI(
        title="Fitness Index ML Service",
        version="1.0.0",
    )
    app.state.settings = resolved_settings
    if model_artifacts is not None:
        app.state.model_artifacts = model_artifacts

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/predict", response_model=PredictionResponse)
    async def predict(payload: PredictionRequest, raw_request: Request) -> PredictionResponse:
        logger.info("Prediction request received for athlete_id=%s", payload.athlete_id or "unknown")
        try:
            settings_from_app: MLServiceSettings = raw_request.app.state.settings
            artifacts: ModelArtifacts | None = getattr(raw_request.app.state, "model_artifacts", None)
            if artifacts is None:
                artifacts = load_model_artifacts(settings_from_app)
                raw_request.app.state.model_artifacts = artifacts

            return await run_in_threadpool(
                _predict_sync,
                payload,
                artifacts,
                settings_from_app,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ModelLoadingError as exc:
            logger.exception("Failed to initialize model artifacts")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Unexpected prediction failure")
            raise HTTPException(status_code=500, detail="Prediction failed") from exc

    return app


def _predict_sync(
    payload: PredictionRequest,
    artifacts: ModelArtifacts,
    settings: MLServiceSettings,
) -> PredictionResponse:
    prepared = prepare_inference_input(payload, settings)
    prediction = run_prediction_pipeline(
        prepared=prepared,
        models=artifacts,
        settings=settings,
    )
    recommendations = build_recommendations(prepared=prepared, prediction=prediction)
    return PredictionResponse(
        fitness_index=round(prediction.fitness_index, 2),
        fatigue_risk=round(prediction.fatigue_risk, 2),
        trend=prediction.trend,
        recommendations=recommendations,
    )


def _configure_logging(level: str) -> None:
    root_logger = logging.getLogger()
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    if not root_logger.handlers:
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        root_logger.setLevel(resolved_level)


app = create_app()
