from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from ml_service.services.bootstrap_models import (
    TrainedTimesFMRegressorWrapper,
    _extract_tensor,
    _load_timesfm_backbone,
    _run_timesfm_backbone,
)


@dataclass(slots=True)
class SequenceSplit:
    features: np.ndarray
    target: np.ndarray


@dataclass(slots=True)
class FeatureSplit:
    features: np.ndarray
    target: np.ndarray


class FeatureDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(self, split: FeatureSplit) -> None:
        self.features = torch.as_tensor(split.features, dtype=torch.float32)
        self.target = torch.as_tensor(split.target, dtype=torch.float32).reshape(-1, 1)

    def __len__(self) -> int:
        return self.features.shape[0]

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.features[index], self.target[index]


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    models_dir = args.models_dir.resolve()
    artifact_path = models_dir / "timesfm.pt"
    report_path = models_dir / "timesfm_training_report.json"
    backbone_dir = models_dir / "timesfm_backbone"

    if not backbone_dir.exists():
        raise SystemExit(
            f"TimesFM backbone directory was not found at {backbone_dir}. "
            "Run ml_service.scripts.download_export_models first."
        )

    train_split = load_sequence_split(dataset_dir / "sequence_train.npz", target_name=args.target_name)
    val_split = load_sequence_split(dataset_dir / "sequence_val.npz", target_name=args.target_name)
    test_split = load_sequence_split(dataset_dir / "sequence_test.npz", target_name=args.target_name)
    train_split = maybe_limit_split(train_split, max_samples=args.max_samples_per_split, seed=args.random_state)
    val_split = maybe_limit_split(val_split, max_samples=args.max_samples_per_split, seed=args.random_state + 1)
    test_split = maybe_limit_split(test_split, max_samples=args.max_samples_per_split, seed=args.random_state + 2)

    device = torch.device("cuda" if torch.cuda.is_available() and not args.force_cpu else "cpu")
    print(f"Extracting TimesFM forecast features on device={device} ...")
    train_features = extract_regression_features(
        split_name="train",
        sequences=train_split.features,
        backbone_dir=backbone_dir,
        loader_kind=args.loader_kind,
        frequency=args.frequency,
        recent_window=args.recent_window,
        batch_size=args.feature_batch_size,
        device=device,
    )
    val_features = extract_regression_features(
        split_name="val",
        sequences=val_split.features,
        backbone_dir=backbone_dir,
        loader_kind=args.loader_kind,
        frequency=args.frequency,
        recent_window=args.recent_window,
        batch_size=args.feature_batch_size,
        device=device,
    )
    test_features = extract_regression_features(
        split_name="test",
        sequences=test_split.features,
        backbone_dir=backbone_dir,
        loader_kind=args.loader_kind,
        frequency=args.frequency,
        recent_window=args.recent_window,
        batch_size=args.feature_batch_size,
        device=device,
    )

    feature_train_split = FeatureSplit(features=train_features, target=train_split.target)
    feature_val_split = FeatureSplit(features=val_features, target=val_split.target)
    feature_test_split = FeatureSplit(features=test_features, target=test_split.target)

    forecast_dim = int(train_features.shape[1] - 1)
    model = build_model(forecast_dim=forecast_dim, backbone_dir=backbone_dir, args=args).to(device)
    optimizer = torch.optim.AdamW(
        model.regression_head.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    criterion = nn.MSELoss()

    train_loader = DataLoader(FeatureDataset(feature_train_split), batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(FeatureDataset(feature_val_split), batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(FeatureDataset(feature_test_split), batch_size=args.batch_size, shuffle=False)

    best_state: dict[str, torch.Tensor] | None = None
    best_val_rmse = float("inf")
    epochs_without_improvement = 0
    history: list[dict[str, float]] = []

    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            criterion=criterion,
            device=device,
        )
        val_metrics = evaluate(model=model, loader=val_loader, device=device)
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 6),
                "val_mae": round(val_metrics["mae"], 6),
                "val_rmse": round(val_metrics["rmse"], 6),
                "val_r2": round(val_metrics["r2"], 6),
            }
        )
        print(
            f"epoch={epoch} "
            f"train_loss={train_loss:.6f} "
            f"val_mae={val_metrics['mae']:.6f} "
            f"val_rmse={val_metrics['rmse']:.6f} "
            f"val_r2={val_metrics['r2']:.6f}"
        )

        if val_metrics["rmse"] + args.min_delta < best_val_rmse:
            best_val_rmse = val_metrics["rmse"]
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.regression_head.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if epochs_without_improvement >= args.patience:
            break

    if best_state is None:
        raise RuntimeError("TimesFM training did not produce a checkpoint")

    model.regression_head.load_state_dict(best_state)

    train_metrics = evaluate(model=model, loader=train_loader, device=device)
    val_metrics = evaluate(model=model, loader=val_loader, device=device)
    test_metrics = evaluate(model=model, loader=test_loader, device=device)

    model = model.to("cpu")
    model.reset_backbone()
    torch.save(model, artifact_path)

    report = {
        "target_name": args.target_name,
        "device": str(device),
        "config": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "hidden_dim": args.hidden_dim,
            "dropout": args.dropout,
            "loader_kind": args.loader_kind,
            "frequency": args.frequency,
            "recent_window": args.recent_window,
            "patience": args.patience,
            "feature_batch_size": args.feature_batch_size,
            "max_samples_per_split": args.max_samples_per_split,
            "random_state": args.random_state,
        },
        "dataset": {
            "train_rows": int(train_split.features.shape[0]),
            "val_rows": int(val_split.features.shape[0]),
            "test_rows": int(test_split.features.shape[0]),
            "context_length": int(train_split.features.shape[1]),
            "num_input_channels": int(train_split.features.shape[2]),
            "forecast_dim": forecast_dim,
            "regression_feature_dim": int(train_features.shape[1]),
        },
        "train_metrics": round_metrics(train_metrics),
        "val_metrics": round_metrics(val_metrics),
        "test_metrics": round_metrics(test_metrics),
        "history": history,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved TimesFM artifact: {artifact_path}")
    print(f"Saved report: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a lightweight regression head on top of a frozen TimesFM backbone and "
            "export a ml_service-compatible timesfm.pt artifact."
        )
    )
    parser.add_argument("--dataset-dir", type=Path, default=Path("ml_service/datasets"))
    parser.add_argument("--models-dir", type=Path, default=Path("ml_service/models"))
    parser.add_argument("--target-name", default="fitness_index_target")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--loader-kind", default="timesfm2_5")
    parser.add_argument("--frequency", type=int, default=0)
    parser.add_argument("--recent-window", type=int, default=7)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--min-delta", type=float, default=1e-3)
    parser.add_argument("--feature-batch-size", type=int, default=128)
    parser.add_argument("--max-samples-per-split", type=int, default=0)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--force-cpu", action="store_true")
    return parser.parse_args()


def load_sequence_split(path: Path, *, target_name: str) -> SequenceSplit:
    payload = np.load(path, allow_pickle=True)
    return SequenceSplit(
        features=np.asarray(payload["X"], dtype=np.float32),
        target=np.asarray(payload[target_name], dtype=np.float32),
    )


def maybe_limit_split(split: SequenceSplit, *, max_samples: int, seed: int) -> SequenceSplit:
    if max_samples <= 0 or split.features.shape[0] <= max_samples:
        return split

    generator = np.random.default_rng(seed)
    indexes = np.sort(generator.choice(split.features.shape[0], size=max_samples, replace=False))
    print(f"Using subset: kept {len(indexes)} of {split.features.shape[0]} rows")
    return SequenceSplit(
        features=split.features[indexes],
        target=split.target[indexes],
    )


def build_model(
    *,
    forecast_dim: int,
    backbone_dir: Path,
    args: argparse.Namespace,
) -> TrainedTimesFMRegressorWrapper:
    torch.manual_seed(args.random_state)
    np.random.seed(args.random_state)
    return TrainedTimesFMRegressorWrapper(
        backbone_dir=str(backbone_dir),
        loader_kind=args.loader_kind,
        forecast_dim=forecast_dim,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        frequency=args.frequency,
        recent_window=args.recent_window,
    )


@torch.no_grad()
def extract_regression_features(
    *,
    split_name: str,
    sequences: np.ndarray,
    backbone_dir: Path,
    loader_kind: str,
    frequency: int,
    recent_window: int,
    batch_size: int,
    device: torch.device,
) -> np.ndarray:
    backbone = _load_timesfm_backbone(str(backbone_dir), loader_kind).to(device)
    backbone.eval()
    extracted: list[np.ndarray] = []
    total_batches = max(1, (sequences.shape[0] + batch_size - 1) // batch_size)

    for batch_index, start in enumerate(range(0, sequences.shape[0], batch_size), start=1):
        end = min(start + batch_size, sequences.shape[0])
        print(
            f"[{split_name}] extracting batch {batch_index}/{total_batches} "
            f"rows={start}:{end}"
        )
        batch = torch.as_tensor(sequences[start:end], dtype=torch.float32, device=device)
        univariate = batch.mean(dim=-1)
        recent_context = univariate[:, -min(recent_window, univariate.shape[1]) :].mean(dim=1, keepdim=True)
        outputs = _run_timesfm_backbone(
            model=backbone,
            loader_kind=loader_kind,
            univariate=univariate,
            frequency=frequency,
        )
        forecast = _extract_tensor(outputs, preferred=("mean_predictions", "full_predictions"))
        if forecast is None:
            raise RuntimeError("TimesFM backbone did not expose forecast tensors")
        forecast_features = forecast.reshape(forecast.shape[0], -1).float()
        regression_features = torch.cat((forecast_features, recent_context.float()), dim=1)
        extracted.append(regression_features.detach().cpu().numpy())

    if not extracted:
        return np.empty((0, 0), dtype=np.float32)

    return np.concatenate(extracted, axis=0).astype(np.float32, copy=False)


def train_epoch(
    *,
    model: TrainedTimesFMRegressorWrapper,
    loader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    total_examples = 0
    for features, target in loader:
        features = features.to(device)
        target = target.to(device)
        optimizer.zero_grad(set_to_none=True)
        prediction = model.regression_head(features)
        loss = criterion(prediction, target)
        loss.backward()
        optimizer.step()

        total_loss += float(loss.detach().cpu()) * features.shape[0]
        total_examples += features.shape[0]
    return total_loss / max(1, total_examples)


@torch.no_grad()
def evaluate(
    *,
    model: TrainedTimesFMRegressorWrapper,
    loader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
    device: torch.device,
) -> dict[str, float]:
    model.eval()
    predictions: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    for features, target in loader:
        features = features.to(device)
        prediction = model.regression_head(features).detach().cpu().numpy().reshape(-1)
        predictions.append(prediction)
        targets.append(target.detach().cpu().numpy().reshape(-1))

    if not predictions:
        return {"mae": 0.0, "rmse": 0.0, "r2": 0.0}

    y_pred = np.concatenate(predictions)
    y_true = np.concatenate(targets)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 0.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return {"mae": mae, "rmse": rmse, "r2": r2}


def round_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 6) for key, value in metrics.items()}


if __name__ == "__main__":
    main()
