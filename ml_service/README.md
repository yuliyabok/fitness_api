# ML Service

Отдельный FastAPI-сервис для расчета `fitness_index`, `fatigue_risk`,
`trend` и рекомендаций на основе:

- табличных метрик спортсмена
- временных рядов тренировок, сна, SpO2 и давления
- sequence-моделей `PatchTST` и `TimesFM`

## Что лежит в `models/`

Сервис ожидает такие артефакты:

- `timesfm.pt`
- `patchtst.pt`
- `load_model.pkl`
- `recovery_model.pkl`
- `cardio_model.pkl`
- `scaler.pkl`

Если часть файлов отсутствует и включен `ALLOW_MISSING_MODELS=true`, сервис
использует встроенный heuristic fallback.

## Bootstrap-вариант без дообучения

Для старта можно скачать публичные foundation-модели из Hugging Face и
экспортировать совместимые адаптеры:

- `TimesFM`: официальный Google checkpoint
- `PatchTST`: safetensors-совместимый checkpoint `ibm-research/testing-patchtst_etth1_pretrain`

Скрипт создаст:

- `ml_service/models/timesfm.pt`
- `ml_service/models/patchtst.pt`
- `ml_service/models/timesfm_backbone/`
- `ml_service/models/patchtst_backbone/`
- `ml_service/models/bootstrap_manifest.json`

Важно: это только bootstrap для sequence-моделей. Он не заменяет ваши
доменные `load_model.pkl`, `recovery_model.pkl`, `cardio_model.pkl`,
`scaler.pkl`.

### Команда экспорта

```bash
cd /home/yuliya/diplom/fitness_api
python3 -m venv .venv-ml
.venv-ml/bin/pip install -r ml_service/requirements.txt
PYTHONPATH=/home/yuliya/diplom/fitness_api .venv-ml/bin/python -m ml_service.scripts.download_export_models --models-dir ml_service/models
```

Примечания:

- для скачивания нужен доступ в интернет
- под `TimesFM` нужно заметное место на диске
- после этого tabular-модели все равно останутся project-specific

## Временные tabular `.pkl` без дообучения

Чтобы `ml_service` мог работать без fallback по tabular-части уже сейчас,
можно сгенерировать временные bootstrap-артефакты:

- `load_model.pkl`
- `recovery_model.pkl`
- `cardio_model.pkl`
- `scaler.pkl`

Команда:

```bash
cd /home/yuliya/diplom/fitness_api
PYTHONPATH=/home/yuliya/diplom/fitness_api python3 -m ml_service.scripts.export_bootstrap_tabular_artifacts --models-dir ml_service/models
```

Скрипт создаст файлы в `ml_service/models/` и `bootstrap_tabular_manifest.json`.
Эти `.pkl` совместимы с текущим `model_loader.py`, но остаются временным
решением до настоящего обучения на ваших данных.

Если вы хотите убрать fallback полностью, порядок такой:

1. Скачать и экспортировать `timesfm.pt` и `patchtst.pt`
2. Сгенерировать временные `load/recovery/cardio/scaler`
3. Поставить `ALLOW_MISSING_MODELS=false`

## Конфигурация

Скопируйте `.env.example` в `.env` и задайте значения:

- `TIMESFM_MODEL_PATH`
- `PATCHTST_MODEL_PATH`
- `LOAD_MODEL_PATH`
- `RECOVERY_MODEL_PATH`
- `CARDIO_MODEL_PATH`
- `SCALER_PATH`
- `WINDOW_SIZE`
- `USE_DUMMY_MODELS`
- `ALLOW_MISSING_MODELS`
- `LOG_LEVEL`

Рекомендуемые режимы:

- локальная разработка: `USE_DUMMY_MODELS=false`, `ALLOW_MISSING_MODELS=true`
- строгая проверка артефактов: `USE_DUMMY_MODELS=false`, `ALLOW_MISSING_MODELS=false`

## Локальный запуск

```bash
cd /home/yuliya/diplom/fitness_api
python3 -m venv .venv-ml
.venv-ml/bin/pip install -r ml_service/requirements.txt
PYTHONPATH=/home/yuliya/diplom/fitness_api .venv-ml/bin/uvicorn ml_service.main:app --host 0.0.0.0 --port 9000
```

## Docker

В каталоге `ml_service` подготовлен [Dockerfile](/home/yuliya/diplom/fitness_api/ml_service/Dockerfile).

Пример локальной сборки:

```bash
cd /home/yuliya/diplom/fitness_api
docker build -f ml_service/Dockerfile -t fitness-ml-service .
docker run --rm -p 9000:9000 --env-file ml_service/.env fitness-ml-service
```
