from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from transformers import PatchTSTConfig, PatchTSTForRegression

from ml_service.services.bootstrap_models import TrainedPatchTSTRegressorWrapper


@dataclass(slots=True)
class SequenceSplit:
    features: np.ndarray
    target: np.ndarray


class SequenceDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(self, split: SequenceSplit) -> None:
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
    backbone_dir = models_dir / "patchtst_backbone"
    artifact_path = models_dir / "patchtst.pt"
    report_path = models_dir / "patchtst_training_report.json"
    models_dir.mkdir(parents=True, exist_ok=True)

    train_split = load_sequence_split(dataset_dir / "sequence_train.npz", target_name=args.target_name)
    val_split = load_sequence_split(dataset_dir / "sequence_val.npz", target_name=args.target_name)
    test_split = load_sequence_split(dataset_dir / "sequence_test.npz", target_name=args.target_name)

    device = torch.device("cuda" if torch.cuda.is_available() and not args.force_cpu else "cpu")
    model = build_model(train_split, args=args).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    criterion = nn.MSELoss()

    train_loader = DataLoader(
        SequenceDataset(train_split),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        SequenceDataset(val_split),
        batch_size=args.batch_size,
        shuffle=False,
    )
    test_loader = DataLoader(
        SequenceDataset(test_split),
        batch_size=args.batch_size,
        shuffle=False,
    )

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

        if val_metrics["rmse"] + args.min_delta < best_val_rmse:
            best_val_rmse = val_metrics["rmse"]
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        print(
            f"epoch={epoch} "
            f"train_loss={train_loss:.6f} "
            f"val_mae={val_metrics['mae']:.6f} "
            f"val_rmse={val_metrics['rmse']:.6f} "
            f"val_r2={val_metrics['r2']:.6f}"
        )

        if epochs_without_improvement >= args.patience:
            break

    if best_state is None:
        raise RuntimeError("PatchTST training did not produce a checkpoint")

    model.load_state_dict(best_state)
    model.save_pretrained(str(backbone_dir), safe_serialization=True)
    torch.save(
        TrainedPatchTSTRegressorWrapper(backbone_dir=str(backbone_dir)),
        artifact_path,
    )

    train_metrics = evaluate(model=model, loader=train_loader, device=device)
    val_metrics = evaluate(model=model, loader=val_loader, device=device)
    test_metrics = evaluate(model=model, loader=test_loader, device=device)

    report = {
        "target_name": args.target_name,
        "device": str(device),
        "config": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "patch_length": args.patch_length,
            "patch_stride": args.patch_stride,
            "d_model": args.d_model,
            "num_hidden_layers": args.num_hidden_layers,
            "num_attention_heads": args.num_attention_heads,
            "dropout": args.dropout,
            "head_dropout": args.head_dropout,
            "patience": args.patience,
            "random_state": args.random_state,
        },
        "dataset": {
            "train_rows": int(train_split.features.shape[0]),
            "val_rows": int(val_split.features.shape[0]),
            "test_rows": int(test_split.features.shape[0]),
            "context_length": int(train_split.features.shape[1]),
            "num_input_channels": int(train_split.features.shape[2]),
        },
        "train_metrics": round_metrics(train_metrics),
        "val_metrics": round_metrics(val_metrics),
        "test_metrics": round_metrics(test_metrics),
        "history": history,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved PatchTST backbone: {backbone_dir}")
    print(f"Saved PatchTST artifact: {artifact_path}")
    print(f"Saved report: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train PatchTSTForRegression on the generated sequence dataset and export a "
            "ml_service-compatible patchtst.pt artifact."
        )
    )
    parser.add_argument("--dataset-dir", type=Path, default=Path("ml_service/datasets"))
    parser.add_argument("--models-dir", type=Path, default=Path("ml_service/models"))
    parser.add_argument("--target-name", default="fitness_index_target")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patch-length", type=int, default=5)
    parser.add_argument("--patch-stride", type=int, default=5)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--num-hidden-layers", type=int, default=2)
    parser.add_argument("--num-attention-heads", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--head-dropout", type=float, default=0.1)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--min-delta", type=float, default=1e-3)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--force-cpu", action="store_true")
    return parser.parse_args()


def load_sequence_split(path: Path, *, target_name: str) -> SequenceSplit:
    payload = np.load(path, allow_pickle=True)
    return SequenceSplit(
        features=np.asarray(payload["X"], dtype=np.float32),
        target=np.asarray(payload[target_name], dtype=np.float32),
    )


def build_model(split: SequenceSplit, *, args: argparse.Namespace) -> PatchTSTForRegression:
    torch.manual_seed(args.random_state)
    np.random.seed(args.random_state)
    context_length = int(split.features.shape[1])
    num_input_channels = int(split.features.shape[2])

    config = PatchTSTConfig(
        context_length=context_length,
        patch_length=args.patch_length,
        patch_stride=args.patch_stride,
        d_model=args.d_model,
        num_hidden_layers=args.num_hidden_layers,
        num_attention_heads=args.num_attention_heads,
        num_input_channels=num_input_channels,
        num_targets=1,
        prediction_length=1,
        dropout=args.dropout,
        head_dropout=args.head_dropout,
        loss="mse",
        pooling_type="mean",
        scaling="std",
        use_cls_token=False,
    )
    return PatchTSTForRegression(config)


def train_epoch(
    *,
    model: PatchTSTForRegression,
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
        output = model(
            past_values=features,
            return_dict=True,
        )
        prediction = output.regression_outputs
        loss = criterion(prediction, target)
        loss.backward()
        optimizer.step()

        total_loss += float(loss.detach().cpu()) * features.shape[0]
        total_examples += features.shape[0]

    return total_loss / max(1, total_examples)


@torch.no_grad()
def evaluate(
    *,
    model: PatchTSTForRegression,
    loader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
    device: torch.device,
) -> dict[str, float]:
    model.eval()
    predictions: list[np.ndarray] = []
    targets: list[np.ndarray] = []

    for features, target in loader:
        features = features.to(device)
        output = model(
            past_values=features,
            return_dict=True,
        )
        prediction = output.regression_outputs.detach().cpu().numpy().reshape(-1)
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
