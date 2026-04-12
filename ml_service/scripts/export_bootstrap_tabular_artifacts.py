from __future__ import annotations

import argparse
import json
import logging
import pickle
from pathlib import Path
from typing import Any

from ml_service.services.bootstrap_tabular import BootstrapTabularModel, BootstrapTabularScaler

try:
    import joblib
except ImportError:  # pragma: no cover - optional during minimal local setup
    joblib = None

logger = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    export_artifacts(models_dir=args.models_dir, force=args.force)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export temporary bootstrap artifacts for load_model.pkl, "
            "recovery_model.pkl, cardio_model.pkl and scaler.pkl."
        )
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("ml_service/models"),
        help="Directory where the `.pkl` bootstrap artifacts will be stored.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing bootstrap `.pkl` files.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level.",
    )
    return parser.parse_args()


def export_artifacts(*, models_dir: Path, force: bool = False) -> dict[str, str]:
    models_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {
        "load_model.pkl": BootstrapTabularModel("load"),
        "recovery_model.pkl": BootstrapTabularModel("recovery"),
        "cardio_model.pkl": BootstrapTabularModel("cardio"),
        "scaler.pkl": BootstrapTabularScaler(),
    }
    manifest: dict[str, str] = {}

    for file_name, artifact in artifacts.items():
        target_path = models_dir / file_name
        if target_path.exists() and not force:
            logger.info("Skipping %s because it already exists", target_path)
            manifest[file_name] = str(target_path)
            continue
        _dump_artifact(target_path, artifact)
        manifest[file_name] = str(target_path)
        logger.info("Created bootstrap tabular artifact: %s", target_path)

    manifest_path = models_dir / "bootstrap_tabular_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifacts": manifest,
                "note": (
                    "These `.pkl` files are deterministic bootstrap artifacts that keep "
                    "ml_service running without fallback. They are not a substitute for "
                    "real domain-trained tabular models."
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("Manifest: %s", manifest_path)
    return manifest


def _dump_artifact(path: Path, artifact: Any) -> None:
    if joblib is not None:
        joblib.dump(artifact, path)
        return
    with path.open("wb") as file_obj:
        pickle.dump(artifact, file_obj)


if __name__ == "__main__":
    main()
