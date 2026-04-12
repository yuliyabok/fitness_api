from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

try:
    from sklearn.metrics import root_mean_squared_error
except ImportError:  # pragma: no cover - compatibility fallback
    root_mean_squared_error = None
from sklearn.preprocessing import StandardScaler

from ml_service.config import TABULAR_FEATURE_NAMES

MODEL_TARGETS = {
    "load_model.pkl": "load_score_target",
    "recovery_model.pkl": "recovery_score_target",
    "cardio_model.pkl": "cardio_score_target",
}


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    models_dir = args.models_dir.resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    train_features, train_targets = load_tabular_split(dataset_dir / "tabular_train.csv")
    val_features, val_targets = load_tabular_split(dataset_dir / "tabular_val.csv")
    test_features, test_targets = load_tabular_split(dataset_dir / "tabular_test.csv")

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_features)
    val_scaled = scaler.transform(val_features) if len(val_features) else np.empty((0, train_scaled.shape[1]))
    test_scaled = scaler.transform(test_features) if len(test_features) else np.empty((0, train_scaled.shape[1]))

    report = {
        "config": {
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "min_samples_leaf": args.min_samples_leaf,
            "random_state": args.random_state,
        },
        "dataset": {
            "train_rows": int(train_scaled.shape[0]),
            "val_rows": int(val_scaled.shape[0]),
            "test_rows": int(test_scaled.shape[0]),
            "feature_names": list(TABULAR_FEATURE_NAMES),
        },
        "models": {},
    }

    for artifact_name, target_name in MODEL_TARGETS.items():
        model = RandomForestRegressor(
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            min_samples_leaf=args.min_samples_leaf,
            n_jobs=-1,
            random_state=args.random_state,
        )
        model.fit(train_scaled, train_targets[target_name])

        model_path = models_dir / artifact_name
        joblib.dump(model, model_path)

        report["models"][artifact_name] = {
            "target_name": target_name,
            "feature_importances": {
                feature_name: round(float(importance), 6)
                for feature_name, importance in sorted(
                    zip(TABULAR_FEATURE_NAMES, model.feature_importances_, strict=True),
                    key=lambda item: item[1],
                    reverse=True,
                )
            },
            "train_metrics": evaluate_regression(model, train_scaled, train_targets[target_name]),
            "val_metrics": evaluate_regression(model, val_scaled, val_targets[target_name]),
            "test_metrics": evaluate_regression(model, test_scaled, test_targets[target_name]),
        }

    scaler_path = models_dir / "scaler.pkl"
    joblib.dump(scaler, scaler_path)

    report_path = models_dir / "tabular_training_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved scaler: {scaler_path}")
    for artifact_name in MODEL_TARGETS:
        print(f"Saved model: {models_dir / artifact_name}")
    print(f"Saved report: {report_path}")

    for artifact_name, metrics in report["models"].items():
        print(
            f"{artifact_name}: "
            f"val_mae={metrics['val_metrics']['mae']} "
            f"val_rmse={metrics['val_metrics']['rmse']} "
            f"val_r2={metrics['val_metrics']['r2']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train tabular baseline models for load, recovery and cardio scores from the "
            "generated dataset splits, then export scaler.pkl and model artifacts for ml_service."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("ml_service/datasets"),
        help="Directory containing tabular_train.csv, tabular_val.csv and tabular_test.csv.",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("ml_service/models"),
        help="Directory where scaler.pkl and trained model artifacts will be stored.",
    )
    parser.add_argument("--n-estimators", type=int, default=300, help="RandomForestRegressor n_estimators.")
    parser.add_argument("--max-depth", type=int, default=10, help="RandomForestRegressor max_depth.")
    parser.add_argument("--min-samples-leaf", type=int, default=2, help="RandomForestRegressor min_samples_leaf.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for reproducible training.")
    return parser.parse_args()


def load_tabular_split(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    rows: list[list[float]] = []
    targets: dict[str, list[float]] = {target_name: [] for target_name in MODEL_TARGETS.values()}

    with path.open("r", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for raw_row in reader:
            rows.append([float(raw_row[name]) for name in TABULAR_FEATURE_NAMES])
            for target_name in targets:
                targets[target_name].append(float(raw_row[target_name]))

    feature_matrix = np.asarray(rows, dtype=np.float32) if rows else np.empty((0, len(TABULAR_FEATURE_NAMES)), dtype=np.float32)
    target_arrays = {
        target_name: np.asarray(values, dtype=np.float32)
        for target_name, values in targets.items()
    }
    return feature_matrix, target_arrays


def evaluate_regression(model: RandomForestRegressor, features: np.ndarray, target: np.ndarray) -> dict[str, float | None]:
    if len(features) == 0:
        return {"mae": None, "rmse": None, "r2": None}
    predictions = model.predict(features)
    rmse_value = (
        float(root_mean_squared_error(target, predictions))
        if root_mean_squared_error is not None
        else float(np.sqrt(np.mean((target - predictions) ** 2)))
    )
    return {
        "mae": round(float(mean_absolute_error(target, predictions)), 6),
        "rmse": round(rmse_value, 6),
        "r2": round(float(r2_score(target, predictions)), 6),
    }


if __name__ == "__main__":
    main()
