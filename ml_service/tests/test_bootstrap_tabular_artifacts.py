from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml_service.scripts.export_bootstrap_tabular_artifacts import export_artifacts

try:
    import joblib
except ImportError:  # pragma: no cover - optional during minimal local setup
    joblib = None

import pickle


class BootstrapTabularArtifactsTests(unittest.TestCase):
    def test_export_artifacts_creates_all_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            models_dir = Path(tmp_dir_name)

            manifest = export_artifacts(models_dir=models_dir, force=False)

            self.assertEqual(
                set(manifest),
                {"load_model.pkl", "recovery_model.pkl", "cardio_model.pkl", "scaler.pkl"},
            )
            for file_name in manifest:
                self.assertTrue((models_dir / file_name).exists())
            self.assertTrue((models_dir / "bootstrap_tabular_manifest.json").exists())

    def test_exported_models_can_transform_and_predict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            models_dir = Path(tmp_dir_name)
            export_artifacts(models_dir=models_dir, force=True)

            scaler = _load(models_dir / "scaler.pkl")
            load_model = _load(models_dir / "load_model.pkl")
            recovery_model = _load(models_dir / "recovery_model.pkl")
            cardio_model = _load(models_dir / "cardio_model.pkl")

            row = [[65.0, 62.0, 1.08, 78.0, 7.8, 88.0, 138.0, 172.0, 98.0, 118.0, 76.0, 8.0, 28.0, 71.0, 178.0]]
            transformed = scaler.transform(row)

            load_value = float(_first(load_model.predict(transformed)))
            recovery_value = float(_first(recovery_model.predict(transformed)))
            cardio_value = float(_first(cardio_model.predict(transformed)))

            self.assertGreaterEqual(load_value, 0.0)
            self.assertLessEqual(load_value, 100.0)
            self.assertGreaterEqual(recovery_value, 0.0)
            self.assertLessEqual(recovery_value, 100.0)
            self.assertGreaterEqual(cardio_value, 0.0)
            self.assertLessEqual(cardio_value, 100.0)


def _load(path: Path):
    if joblib is not None:
        return joblib.load(path)
    with path.open("rb") as file_obj:
        return pickle.load(file_obj)


def _first(values) -> float:
    if hasattr(values, "tolist"):
        values = values.tolist()
    return values[0]


if __name__ == "__main__":
    unittest.main()
