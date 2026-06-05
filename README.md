# Fitness API + ML Service

Этот репозиторий содержит серверную часть проекта анализа физического состояния спортсмена. Здесь находятся:

- `backend/` — основной FastAPI backend с PostgreSQL
- `ml_service/` — отдельный FastAPI сервис для расчёта `fitness_index`
- `docker-compose.yml` — локальный запуск сервисов через Docker

Мобильное Flutter-приложение находится отдельно, в соседнем каталоге `../fitness_app`.

## Что делает проект

Система собирает данные спортсмена:

- тренировки
- сон
- артериальное давление
- SpO2
- дополнительные аналитические записи

После этого backend:

1. сохраняет данные в PostgreSQL,
2. собирает историю спортсмена,
3. отправляет её в `ml_service`,
4. получает рассчитанный `fitness_index`, `fatigue_risk`, `trend` и рекомендации,
5. сохраняет результат в таблицу `fitness_scores`.

## Архитектура

```text
Flutter app
   ->
backend (FastAPI)
   -> PostgreSQL
   -> ml_service (FastAPI)
   -> fitness_scores
   ->
Flutter app
```

Чуть подробнее:

- Flutter работает как клиентский интерфейс спортсмена и тренера.
- `backend` отвечает за авторизацию, CRUD-операции, доступ к БД и orchestration AI-запросов.
- `ml_service` отвечает только за ML-предобработку, инференс и генерацию рекомендаций.
- PostgreSQL хранит пользователей, профили, тренировки, показатели здоровья и результаты AI.

## Структура репозитория

```text
fitness_api/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # REST endpoints
│   │   ├── models/              # SQLAlchemy модели
│   │   ├── schemas/             # Pydantic схемы
│   │   └── services/            # бизнес-логика, включая AI orchestration
│   ├── alembic/                 # миграции БД
│   ├── tests/
│   └── start.sh
├── ml_service/
│   ├── services/                # preprocessing, inference, model loading
│   ├── models/                  # .pkl / .pt артефакты и training reports
│   ├── training/                # построение датасета и обучение
│   └── main.py
├── docker-compose.yml
└── render.yaml
```

## Как всё связано по коду

### Backend

Основные маршруты:

- `backend/app/api/routes/auth.py`
- `backend/app/api/routes/trainings.py`
- `backend/app/api/routes/sleep.py`
- `backend/app/api/routes/blood_pressure.py`
- `backend/app/api/routes/spo2.py`
- `backend/app/api/routes/ai.py`

Основной сервис AI-интеграции:

- `backend/app/services/fitness_ai_service.py`

Ключевые функции:

- `build_prediction_payload()` — собирает профиль, тренировки, сон, давление и SpO2 в единый payload
- `predict_and_store_fitness_score()` — вызывает `ml_service` и сохраняет результат в `fitness_scores`

### ML service

Точка входа:

- `ml_service/main.py`

Основные модули:

- `ml_service/services/preprocessing.py`
- `ml_service/services/inference.py`
- `ml_service/services/recommendation_engine.py`
- `ml_service/services/model_loader.py`

Ключевые шаги:

1. `prepare_inference_input()` — строит tabular и sequence признаки
2. `run_prediction_pipeline()` — считает промежуточные оценки и итоговый `fitness_index`
3. `build_recommendations()` — генерирует текстовые рекомендации

## Как считается индекс формы

Расчёт расположен в:

- `ml_service/services/inference.py`

Алгоритм использует:

- tabular модели:
  - `load_model.pkl`
  - `recovery_model.pkl`
  - `cardio_model.pkl`
- sequence модели:
  - `patchtst.pt`
  - `timesfm.pt`

После предобработки сервис считает:

- `load_score`
- `recovery_score`
- `cardio_score`
- `patchtst_score`
- `timesfm_score`

Итоговый `fitness_index` вычисляется как взвешенная комбинация:

```text
0.22 * load_score
+ 0.26 * recovery_score
+ 0.18 * cardio_score
+ 0.17 * patchtst_score
+ 0.17 * timesfm_score
+ trend_adjustment
```

Дополнительно считаются:

- `fatigue_risk`
- `trend`
- `recommendations`

## Какие данные используются в ML

На вход `ml_service` backend передаёт:

- профиль спортсмена
- список тренировок
- список записей сна
- список измерений давления
- список измерений SpO2

В предобработке строятся:

- агрегированные tabular признаки
- последовательность длиной `30` дней

Основные tabular признаки:

- `recent_training_load`
- `chronic_training_load`
- `acute_chronic_ratio`
- `training_consistency`
- `avg_sleep_hours`
- `sleep_consistency`
- `avg_avg_hr`
- `avg_max_hr`
- `avg_spo2`
- `avg_systolic`
- `avg_diastolic`
- `avg_feeling_score`
- `athlete_age`
- `athlete_weight_kg`
- `athlete_height_cm`

Sequence-признаки по дням:

- `training_load`
- `sleep_hours`
- `recovery_signal`
- `cardio_signal`
- `avg_hr`
- `max_hr`
- `spo2`
- `feeling_score`

## База данных

Главные сущности backend:

- `app_users`
- `athlete_profiles`
- `coach_profiles`
- `coach_athlete_links`
- `trainings`
- `sleep_entries`
- `blood_pressure_entries`
- `spo2_entries`
- `analysis_entries`
- `calorie_entries`
- `cycle_events`
- `cycle_settings`
- `fitness_scores`

Практически всё в прикладной части завязано на `athlete_id`.

## Быстрый локальный запуск без Docker

### 1. PostgreSQL

Нужно, чтобы локально был запущен PostgreSQL и существовала БД:

- база: `fitness`
- пользователь: `fitness`
- пароль: `fitness`

Проверка:

```bash
psql postgresql://fitness:fitness@localhost:5432/fitness -c "select 1;"
```

### 2. Backend

```bash
cd /home/yuliya/diplom/fitness_api/backend
source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://fitness:fitness@localhost:5432/fitness'
export JWT_SECRET='111111'
export AI_SERVICE_URL='http://127.0.0.1:9000'
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/api/health
curl http://192.168.1.74:8000/api/health
```

### 3. ML service

```bash
cd /home/yuliya/diplom/fitness_api
source .venv-ml/bin/activate
PYTHONPATH=/home/yuliya/diplom/fitness_api uvicorn ml_service.main:app --host 0.0.0.0 --port 9000
```

Проверка:

```bash
curl http://127.0.0.1:9000/health
```

### 4. Для телефона в одной Wi-Fi сети

Если приложение запускается на телефоне, в настройках Flutter-приложения backend должен быть указан так:

```text
http://192.168.1.74:8000
```

Важно:

- backend должен быть поднят с `--host 0.0.0.0`
- телефон и ноутбук должны быть в одной сети
- VPN может ломать локальную маршрутизацию

## Запуск через Docker

Если Docker настроен и группа `docker` работает корректно:

```bash
docker compose up --build
```

Если есть проблемы с группой `docker`, временно можно использовать:

```bash
sudo docker compose up --build
```

## ML-модели и обучение

Обучающие скрипты лежат в:

- `ml_service/training/build_dataset.py`
- `ml_service/training/train_tabular.py`
- `ml_service/training/train_patchtst.py`
- `ml_service/training/train_timesfm.py`

Артефакты моделей лежат в:

- `ml_service/models/`

### Размер датасета

По текущему `dataset_manifest.json`:

- окно истории: `30` дней
- горизонт прогноза: `7` дней
- train: `1392` sample
- val: `312` sample
- test: `312` sample
- всего: `2016` sample

### Tabular-модели

Используется `RandomForestRegressor` для:

- нагрузки
- восстановления
- кардиосостояния

Параметры:

- `n_estimators = 300`
- `max_depth = 10`
- `min_samples_leaf = 2`
- `random_state = 42`

По текущим отчётам лучшей является модель восстановления.

### PatchTST

Используется как sequence-regression модель по временному ряду `30 x 8`.

Ключевые параметры:

- `patch_length = 5`
- `patch_stride = 5`
- `d_model = 64`
- `num_hidden_layers = 2`
- `num_attention_heads = 4`

### TimesFM

Используется как foundation time-series backbone с регрессионной головой сверху.

Сейчас это скорее исследовательская часть архитектуры, чем наиболее сильная модель по качеству.

## Что важно понимать про качество ML

Сейчас система инженерно работает end-to-end:

- данные собираются,
- payload строится,
- `ml_service` вызывается,
- `fitness_index` считается,
- результат сохраняется в БД,
- приложение его отображает.

Но качество моделей пока следует воспринимать как baseline / research stage:

- tabular часть уже стабильнее,
- sequence часть встроена и работает,
- для production-качества дальше нужны реальные данные и более качественная разметка.

## Частые проблемы

### 1. `Connection refused` при входе из приложения

Это почти всегда значит, что backend не отвечает по `http://<ip>:8000`.

Проверьте:

```bash
curl http://127.0.0.1:8000/api/health
curl http://192.168.1.74:8000/api/health
ss -ltnp | grep 8000
```

### 2. Зелёный индикатор backend есть, но данные не пишутся в БД

Индикатор backend означает только то, что `/api/health` отвечает.
Он не гарантирует, что:

- логин успешен,
- токен валиден,
- очередь синхронизации в приложении не битая,
- backend успешно записал данные,
- ML-пересчёт прошёл.

### 3. Локальный аккаунт есть, а серверный логин не работает

Во Flutter есть offline-first поведение. Поэтому аккаунт мог сохраниться только локально на устройстве, но не попасть в PostgreSQL.

В таком случае:

- регистрация визуально выглядит успешной,
- но backend о таком пользователе не знает,
- тренер не сможет найти спортсмена,
- AI/ML тоже не будет работать полноценно.

### 4. В pgAdmin видно ровно 1000 строк

Это не ограничение PostgreSQL.
Обычно это просто лимит отображения строк в интерфейсе pgAdmin.

## Что смотреть в первую очередь, если нужно быстро разобраться

Если нужно за 5 минут понять проект, начните в таком порядке:

1. Этот `README.md`
2. `backend/app/main.py`
3. `backend/app/api/routes/`
4. `backend/app/services/fitness_ai_service.py`
5. `ml_service/main.py`
6. `ml_service/services/preprocessing.py`
7. `ml_service/services/inference.py`
8. `ml_service/models/*training_report.json`

## Полезные локальные README

Внутри проекта уже есть более узкие README:

- `backend/README.md`
- `ml_service/README.md`
- `ml_service/training/README.md`

Этот корневой README нужен как единая карта проекта.
