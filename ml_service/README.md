# ML Service

Отдельный FastAPI-сервис для инференса моделей `TimesFM` и `PatchTST` в проекте
`Fitness Analyzer`.

## Что делает сервис

- загружает ONNX-модели из `models/timesfm.onnx` и `models/patchtst.onnx`
- принимает агрегированные данные спортсмена по HTTP
- формирует временное окно признаков
- нормализует признаки
- запускает выбранную модель по полю `target`
- возвращает `fitness_index` и текстовые рекомендации

## Конфигурация

Скопируйте `.env.example` в `.env` и задайте значения:

- `TIMESFM_MODEL_PATH`
- `PATCHTST_MODEL_PATH`
- `WINDOW_SIZE`
- `DEFAULT_TARGET`
- `NORMALIZATION_MEANS`
- `NORMALIZATION_STDS`
- `USE_DUMMY_MODELS`

`USE_DUMMY_MODELS=true` удобно для локальной разработки и unit-тестов, когда
реальные ONNX-веса ещё не положены в папку `models/`.

## Локальный запуск

```bash
cd /home/yuliya/diplom/fitness_api
python3 -m venv .venv-ml
.venv-ml/bin/pip install -r ml_service/requirements.txt
PYTHONPATH=/home/yuliya/diplom/fitness_api .venv-ml/bin/uvicorn ml_service.main:app --host 0.0.0.0 --port 9000
```

## Docker

В каталоге `ml_service` уже подготовлен [Dockerfile](/home/yuliya/diplom/fitness_api/ml_service/Dockerfile).

Пример локальной сборки:

```bash
cd /home/yuliya/diplom/fitness_api
docker build -f ml_service/Dockerfile -t fitness-ml-service .
docker run --rm -p 9000:9000 --env-file ml_service/.env fitness-ml-service
```
