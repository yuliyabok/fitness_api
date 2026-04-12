from __future__ import annotations

from ml_service.services.inference import PredictionResult
from ml_service.services.preprocessing import PreparedInferenceInput


def build_recommendations(
    *,
    prepared: PreparedInferenceInput,
    prediction: PredictionResult,
) -> list[str]:
    recommendations: list[str] = []
    metrics = prepared.metrics

    if metrics["data_completeness"] < 35.0:
        recommendations.append(
            "Добавьте больше данных по сну, давлению и SpO2 за последние 7-14 дней, чтобы прогноз был точнее."
        )

    if prediction.fatigue_risk >= 70.0:
        recommendations.append(
            "Снизьте интенсивность на ближайшие 24-48 часов и замените одну тяжелую сессию восстановительной."
        )
    elif prediction.fatigue_risk <= 35.0 and prediction.trend == "up":
        recommendations.append(
            "Организм хорошо переносит текущий блок: повышайте объем постепенно, не более чем на 5-10% в неделю."
        )

    if metrics["avg_sleep_hours"] < 7.0:
        recommendations.append(
            "Поднимите среднюю продолжительность сна до 7.5-8 часов: это главный резерв для роста fitness_index."
        )

    if metrics["acute_chronic_ratio"] > 1.25:
        recommendations.append(
            "Текущая нагрузка заметно выше базовой. Добавьте разгрузочный день, чтобы не накапливать усталость."
        )

    if metrics["avg_spo2"] < 95.0:
        recommendations.append(
            "Следите за дыхательным восстановлением и сатурацией; при устойчивом снижении сократите интенсивность."
        )

    if metrics["avg_systolic"] > 130.0 or metrics["avg_diastolic"] > 85.0:
        recommendations.append(
            "Контролируйте давление утром и после интенсивных тренировок, особенно в дни высокой нагрузки."
        )

    if prediction.trend == "down":
        recommendations.append(
            "Тренд снижается: уменьшите плотность тяжелых тренировок и вернитесь к прогрессии после 2-3 спокойных дней."
        )
    elif prediction.trend == "stable" and prediction.fitness_index < 60.0:
        recommendations.append(
            "Сделайте упор на базовую аэробную работу и восстановление, чтобы стабильно поднять форму."
        )

    if not recommendations:
        recommendations.append(
            "Текущий баланс нагрузки и восстановления выглядит устойчивым. Сохраняйте режим и отслеживайте динамику раз в несколько дней."
        )

    return _deduplicate(recommendations)[:4]


def _deduplicate(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
