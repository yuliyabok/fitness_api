# Training Pipeline

## Что делает `build_dataset.py`

Скрипт:

- читает данные спортсменов из PostgreSQL
- агрегирует их в дневные наблюдения
- строит скользящие окна истории длиной `window_size`
- строит proxy-target по будущему горизонту `horizon_days`
- сохраняет `train/val/test` для tabular и sequence обучения

## Какие таблицы используются

- `athlete_profiles`
- `trainings`
- `sleep_entries`
- `blood_pressure_entries`
- `spo2_entries`
- `analysis_entries` как optional label source

## Выходные файлы

В `output-dir` создаются:

- `tabular_train.csv`
- `tabular_val.csv`
- `tabular_test.csv`
- `sequence_train.npz`
- `sequence_val.npz`
- `sequence_test.npz`
- `dataset_manifest.json`

## Как запускать

Скрипт использует SQLAlchemy и ORM backend, поэтому его нужно запускать из
окружения `backend/.venv`:

```bash
cd /home/yuliya/diplom/fitness_api
backend/.venv/bin/python -m ml_service.training.build_dataset --output-dir ml_service/datasets
```

Если нужно собрать датасет по части спортсменов:

```bash
backend/.venv/bin/python -m ml_service.training.build_dataset \
  --athlete-ids "<uuid1>,<uuid2>" \
  --output-dir ml_service/datasets
```

Если данных мало, можно ослабить фильтры:

```bash
backend/.venv/bin/python -m ml_service.training.build_dataset \
  --min-history-completeness 0.05 \
  --min-future-completeness 0.05 \
  --min-samples-per-athlete 1 \
  --output-dir ml_service/datasets
```

## Рекомендуемый порядок обучения

1. Собрать датасет через `build_dataset.py`
2. Проверить `dataset_manifest.json` и размеры split'ов
3. Обучить `scaler.pkl`
4. Обучить `load_model.pkl`, `recovery_model.pkl`, `cardio_model.pkl`
5. Проверить baseline-метрики на `val/test`
6. Только после этого переходить к `PatchTST` и `TimesFM`

## Как обучать tabular baseline

Скрипт:

- читает `tabular_train.csv`, `tabular_val.csv`, `tabular_test.csv`
- обучает `StandardScaler`
- обучает `RandomForestRegressor` отдельно для:
  - `load_score_target`
  - `recovery_score_target`
  - `cardio_score_target`
- сохраняет:
  - `ml_service/models/scaler.pkl`
  - `ml_service/models/load_model.pkl`
  - `ml_service/models/recovery_model.pkl`
  - `ml_service/models/cardio_model.pkl`
  - `ml_service/models/tabular_training_report.json`

Команда:

```bash
cd /home/yuliya/diplom/fitness_api
backend/.venv/bin/python -m ml_service.training.train_tabular \
  --dataset-dir ml_service/datasets \
  --models-dir ml_service/models
```

После этого `ml_service` уже будет использовать настоящие обученные `.pkl`,
а не bootstrap-вариант.

## Как обучать PatchTST

Скрипт:

- читает `sequence_train.npz`, `sequence_val.npz`, `sequence_test.npz`
- обучает `PatchTSTForRegression`
- сохраняет:
  - `ml_service/models/patchtst_backbone/`
  - `ml_service/models/patchtst.pt`
  - `ml_service/models/patchtst_training_report.json`

Команда:

```bash
cd /home/yuliya/diplom/fitness_api
backend/.venv/bin/python -m ml_service.training.train_patchtst \
  --dataset-dir ml_service/datasets \
  --models-dir ml_service/models
```

По умолчанию модель учится на `fitness_index_target`.

## Как обучать TimesFM

Скрипт:

- использует уже скачанный `timesfm_backbone/`
- замораживает backbone
- один раз извлекает forecast-признаки из frozen TimesFM
- обучает только regression-head поверх этих признаков
- сохраняет:
  - `ml_service/models/timesfm.pt`
  - `ml_service/models/timesfm_training_report.json`

Команда:

```bash
cd /home/yuliya/diplom/fitness_api
backend/.venv/bin/python -m ml_service.training.train_timesfm \
  --dataset-dir ml_service/datasets \
  --models-dir ml_service/models \
  --force-cpu
```

Для быстрого CPU-safe прогона на synthetic данных можно ограничить размер
каждого split:

```bash
backend/.venv/bin/python -m ml_service.training.train_timesfm \
  --dataset-dir ml_service/datasets \
  --models-dir ml_service/models \
  --max-samples-per-split 64 \
  --force-cpu
```

Для полноценного fine-tuning на всей выборке лучше использовать GPU: backbone
TimesFM слишком тяжёлый для комфортного полного прогона на CPU.

## Почему сначала tabular baseline

Потому что так проще проверить:

- есть ли в данных signal
- нормальны ли proxy-target
- не течёт ли выборка
- насколько вообще предсказуема задача

Если tabular baseline не даёт вменяемого качества, sequence fine-tuning почти
всегда будет пустой тратой времени.
