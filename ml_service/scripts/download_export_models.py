from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import torch

from ml_service.services.bootstrap_models import (
    BootstrapPatchTSTWrapper,
    BootstrapTimesFMWrapper,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMESFM_MODEL_ID = "google/timesfm-2.5-200m-transformers"
LEGACY_TIMESFM_MODEL_ID = "google/timesfm-2.0-500m-pytorch"
DEFAULT_PATCHTST_MODEL_ID = "ibm-research/testing-patchtst_etth1_pretrain"


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    models_dir = args.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    timesfm_adapter_path = models_dir / "timesfm.pt"
    patchtst_adapter_path = models_dir / "patchtst.pt"

    _export_timesfm(
        model_id=args.timesfm_model_id,
        legacy_model_id=args.legacy_timesfm_model_id,
        backbone_dir=models_dir / "timesfm_backbone",
        adapter_path=timesfm_adapter_path,
        force=args.force,
    )
    _export_patchtst(
        model_id=args.patchtst_model_id,
        backbone_dir=models_dir / "patchtst_backbone",
        adapter_path=patchtst_adapter_path,
        force=args.force,
    )

    manifest = {
        "timesfm": {
            "adapter_path": str(timesfm_adapter_path),
            "backbone_dir": str(models_dir / "timesfm_backbone"),
            "primary_model_id": args.timesfm_model_id,
            "legacy_fallback_model_id": args.legacy_timesfm_model_id,
        },
        "patchtst": {
            "adapter_path": str(patchtst_adapter_path),
            "backbone_dir": str(models_dir / "patchtst_backbone"),
            "model_id": args.patchtst_model_id,
        },
        "note": (
            "This script exports only public foundation-model adapters for timesfm.pt "
            "and patchtst.pt. The project-specific tabular artifacts "
            "load_model.pkl, recovery_model.pkl, cardio_model.pkl and scaler.pkl "
            "still need to be trained or supplied separately."
        ),
    }
    manifest_path = models_dir / "bootstrap_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    logger.info("Bootstrap export finished.")
    logger.info("Created: %s", timesfm_adapter_path)
    logger.info("Created: %s", patchtst_adapter_path)
    logger.info("Manifest: %s", manifest_path)
    logger.warning(
        "Only TimesFM/PatchTST were exported. load_model.pkl, recovery_model.pkl, "
        "cardio_model.pkl and scaler.pkl are still project-specific."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download public TimesFM and PatchTST checkpoints from Hugging Face, "
            "save their local backbone directories, and export lightweight `.pt` adapters "
            "compatible with ml_service."
        )
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("ml_service/models"),
        help="Directory where adapters and local backbone folders will be stored.",
    )
    parser.add_argument(
        "--timesfm-model-id",
        default=DEFAULT_TIMESFM_MODEL_ID,
        help=(
            "Primary Hugging Face model id for TimesFM. "
            "Use a transformers-compatible checkpoint."
        ),
    )
    parser.add_argument(
        "--legacy-timesfm-model-id",
        default=LEGACY_TIMESFM_MODEL_ID,
        help=(
            "Fallback TimesFM model id used when the installed transformers build "
            "does not expose TimesFM 2.5 classes."
        ),
    )
    parser.add_argument(
        "--patchtst-model-id",
        default=DEFAULT_PATCHTST_MODEL_ID,
        help=(
            "Hugging Face model id for PatchTST. "
            "Defaults to a safetensors-compatible checkpoint."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing exported adapters and backbone directories.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level.",
    )
    return parser.parse_args()


def _export_timesfm(
    *,
    model_id: str,
    legacy_model_id: str,
    backbone_dir: Path,
    adapter_path: Path,
    force: bool,
) -> None:
    if adapter_path.exists() and backbone_dir.exists() and not force:
        logger.info("Skipping TimesFM export because %s already exists", adapter_path)
        return

    _ensure_clean_target(backbone_dir, adapter_path, force=force)

    loader_kind, backbone = _load_timesfm_backbone(model_id=model_id, legacy_model_id=legacy_model_id)
    backbone.save_pretrained(str(backbone_dir))

    adapter = BootstrapTimesFMWrapper(
        backbone_dir=str(backbone_dir),
        loader_kind=loader_kind,
    )
    torch.save(adapter, adapter_path)
    logger.info(
        "Exported TimesFM bootstrap adapter: model_id=%s loader_kind=%s path=%s",
        model_id if loader_kind == "timesfm2_5" else legacy_model_id,
        loader_kind,
        adapter_path,
    )


def _export_patchtst(
    *,
    model_id: str,
    backbone_dir: Path,
    adapter_path: Path,
    force: bool,
) -> None:
    if adapter_path.exists() and backbone_dir.exists() and not force:
        logger.info("Skipping PatchTST export because %s already exists", adapter_path)
        return

    _ensure_clean_target(backbone_dir, adapter_path, force=force)

    backbone, resolved_model_id = _load_patchtst_backbone(model_id=model_id)
    backbone.save_pretrained(str(backbone_dir))

    adapter = BootstrapPatchTSTWrapper(backbone_dir=str(backbone_dir))
    torch.save(adapter, adapter_path)
    logger.info(
        "Exported PatchTST bootstrap adapter: model_id=%s path=%s",
        resolved_model_id,
        adapter_path,
    )


def _load_timesfm_backbone(*, model_id: str, legacy_model_id: str) -> tuple[str, torch.nn.Module]:
    try:
        from transformers import TimesFm2_5ModelForPrediction  # type: ignore
    except ImportError:
        TimesFm2_5ModelForPrediction = None

    if TimesFm2_5ModelForPrediction is not None:
        logger.info("Downloading TimesFM 2.5 checkpoint from %s", model_id)
        return "timesfm2_5", TimesFm2_5ModelForPrediction.from_pretrained(model_id)

    from transformers import TimesFmModelForPrediction  # type: ignore

    logger.warning(
        "Installed transformers build does not expose TimesFm2_5ModelForPrediction. "
        "Falling back to legacy checkpoint %s",
        legacy_model_id,
    )
    return "timesfm", TimesFmModelForPrediction.from_pretrained(legacy_model_id)


def _load_patchtst_backbone(*, model_id: str) -> tuple[torch.nn.Module, str]:
    from transformers import AutoModel  # type: ignore

    try:
        logger.info("Downloading PatchTST checkpoint from %s", model_id)
        return AutoModel.from_pretrained(model_id), model_id
    except ValueError as exc:
        if (
            "serious vulnerability issue in `torch.load`" not in str(exc)
            or model_id == DEFAULT_PATCHTST_MODEL_ID
        ):
            raise

        logger.warning(
            "PatchTST checkpoint %s requires torch.load and is blocked by the current "
            "torch/transformers security policy. Falling back to safetensors checkpoint %s",
            model_id,
            DEFAULT_PATCHTST_MODEL_ID,
        )
        return AutoModel.from_pretrained(DEFAULT_PATCHTST_MODEL_ID), DEFAULT_PATCHTST_MODEL_ID


def _ensure_clean_target(backbone_dir: Path, adapter_path: Path, *, force: bool) -> None:
    if force:
        if adapter_path.exists():
            adapter_path.unlink()
        if backbone_dir.exists():
            for child in sorted(
                backbone_dir.rglob("*"),
                key=lambda path: (len(path.parts), str(path)),
                reverse=True,
            ):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            backbone_dir.rmdir()


if __name__ == "__main__":
    main()
