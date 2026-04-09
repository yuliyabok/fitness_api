# Fitness API Backend

FastAPI backend для проекта `Fitness Analyzer`.

Backend отвечает за авторизацию пользователей, хранение данных спортсмена и тренера, а также работу с PostgreSQL через SQLAlchemy.

## Назначение backend

Серверная часть проекта решает такие задачи:

- регистрация спортсмена и тренера
- вход и выдача JWT
- хранение профилей
- хранение тренировок
- хранение анализов
- хранение калорий
- хранение артериального давления
- хранение сна
- хранение SpO2
- хранение данных цикла
- AI-расчет индекса физической формы
- связи тренер-спортсмен

## Технологический стек

- FastAPI
- SQLAlchemy 2
- PostgreSQL
- Alembic
- `PyJWT` для JWT
- `bcrypt` для хеширования паролей
- `pydantic-settings` для конфигурации

## Точка входа

Файл: `app/main.py`

На старте backend:

1. создаёт `FastAPI` приложение
2. читает настройки из `app/core/config.py`
3. настраивает CORS
4. подключает общий роутер `/api`

## Конфигурация

Файл: `app/core/config.py`

Обязательные переменные окружения:

- `DATABASE_URL`
- `JWT_SECRET`

Часто используемые необязательные:

- `CORS_ORIGINS`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `AI_SERVICE_URL`
- `AI_MODEL_TARGET`

`.env` поддерживается.

Можно взять за основу файл [.env.example](/home/yuliya/diplom/fitness_api/backend/.env.example).

`AI_SERVICE_URL` должен указывать на внешний Python ML-сервис. Можно указать как базовый URL
сервиса (`http://127.0.0.1:9000`), так и полный путь (`http://127.0.0.1:9000/predict`).
Backend сам отправляет HTTP `POST` на `/predict` с агрегированными данными спортсмена.

`AI_MODEL_TARGET` задаёт модель по умолчанию для ML-сервиса: `timesfm` или `patchtst`.

ML-сервис возвращает JSON вида:

```json
{
  "fitness_index": 82.4,
  "recommendations": "Сохранить текущий объем сна и добавить один легкий восстановительный день."
}
```

Локально отдельный ML-сервис можно поднять из каталога
[ml_service](/home/yuliya/diplom/fitness_api/ml_service): он предоставляет `POST /predict`
и умеет переключаться между `timesfm` и `patchtst` по полю `target`.

## Локальный запуск

Рабочая папка: `fitness_api/backend`

```bash
python3 -m venv --without-pip .venv
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
.venv/bin/python /tmp/get-pip.py
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
./scripts/run_backend.sh
```

В текущей локальной среде backend настроен на PostgreSQL через `.env`.
Для запуска вручную достаточно:

```bash
./scripts/run_backend.sh
```

Для проверки интеграции с базой и API:

```bash
./scripts/run_integration_checks.sh
```

### Локальный запуск через Docker Compose

Для быстрого старта backend вместе с PostgreSQL можно использовать:

```bash
docker compose up --build
```

После этого:

- PostgreSQL будет доступен на `localhost:5432`
- backend будет доступен на `http://localhost:8000`
- health-check: `GET http://localhost:8000/api/health`

## Публичный деплой для постоянной работы

Для телефона, desktop и web из любой сети лучше использовать публичный backend, а не локальный IP ноутбука.

Рекомендуемый вариант для этого проекта: `Render + Render PostgreSQL`.

Почему этот вариант выбран:

- backend получает постоянный HTTPS-адрес
- данные сохраняются в PostgreSQL на сервере
- Flutter-клиент может работать из любой сети, если есть интернет
- деплой уже подготовлен в виде Blueprint-файла

Файлы деплоя:

- основной Blueprint: [render.yaml](/home/yuliya/diplom/fitness_api/render.yaml)
- дублирующий Blueprint в папке backend: [render.yaml](/home/yuliya/diplom/fitness_api/backend/render.yaml)

В Blueprint уже настроены:

- web service `fitness-api`
- PostgreSQL `fitness-db`
- health check `/api/health`
- автоматическая генерация `JWT_SECRET`
- привязка `DATABASE_URL` к созданной базе

### Как развернуть на Render

1. Загрузите репозиторий `fitness_api` в GitHub.
2. В Render создайте `Blueprint`.
3. Укажите репозиторий и подтвердите создание ресурсов из `render.yaml`.
4. Дождитесь первого деплоя.
5. Получите адрес вида `https://fitness-api.onrender.com`.
6. Передайте этот адрес в Flutter через `FITNESS_API_URL`.

Пример запуска Flutter-клиента:

```bash
cd /home/yuliya/diplom/fitness_app
FITNESS_API_URL=https://fitness-api.onrender.com DEVICE=android ./scripts/run_app.sh
```

### Важные замечания по Render

- В Blueprint выбран `starter` для web service и `basic-256mb` для PostgreSQL, потому что это заметно стабильнее временных dev-туннелей и подходит для постоянного доступа с телефона.
- Для Render Postgres используется стандартный `connectionString`. Backend автоматически приводит `postgres://` и `postgresql://` к формату `postgresql+psycopg://`, который нужен SQLAlchemy c `psycopg`.
- После появления постоянного frontend-домена лучше заменить `CORS_ORIGINS=*` на конкретные адреса, особенно если будет использоваться Flutter Web.

## Smoke tests

В репозитории есть лёгкие contract-smoke-tests на совместимость backend с Flutter:

```bash
python3 -m unittest tests.test_contract_compatibility
```

Они не требуют живой PostgreSQL-базы и проверяют:

- наличие нужных маршрутов
- ожидаемые `201` у create-эндпоинтов
- формат ошибок для клиента
- защиту от тихих ошибок в маршрутах цикла

## Интеграционные тесты

Для интеграционных API-тестов нужен запущенный PostgreSQL и dev-зависимости:

```bash
pip install -r requirements-dev.txt
python -m alembic upgrade head
python3 -m unittest tests.test_api_integration
```

Или одной командой:

```bash
./scripts/run_integration_checks.sh
```

Интеграционные тесты покрывают:

- регистрацию и чтение профиля
- обновление профиля спортсмена
- полный CRUD тренировок
- AI prediction roundtrip и фоновое обновление fitness score
- цикл и обработку ошибок по `kind`
- привязку спортсмена к тренеру и чтение детальной карточки

## Аутентификация

### Регистрация

`POST /api/auth/register`

При регистрации backend:

1. проверяет, что email ещё не занят
2. валидирует пароль
3. создаёт запись в `app_users`
4. создаёт профиль спортсмена или тренера
5. возвращает JWT

### Вход

`POST /api/auth/login`

Backend:

1. ищет пользователя по email
2. проверяет пароль
3. возвращает JWT

### JWT

Используются зависимости:

- `get_current_user`
- `require_athlete`
- `require_coach`

Токен содержит `sub` и `exp`.

## Структура данных

### Пользователи и роли

Таблицы:

- `app_users`
- `athlete_profiles`
- `coach_profiles`
- `coach_athlete_links`

### Данные активности и здоровья

Таблицы:

- `trainings`
- `analysis_entries`
- `calorie_entries`
- `blood_pressure_entries`
- `sleep_entries`
- `spo2_entries`
- `fitness_scores`
- `cycle_events`
- `cycle_settings`

## API маршруты

Главный роутер собирается в `app/api/router.py` и публикуется с префиксом `/api`.

### Служебные

- `GET /api/health`

### Авторизация

- `POST /api/auth/register`
- `POST /api/auth/login`

### Профиль

- `GET /api/profile/me`
- `PUT /api/profile/me`

`PUT /api/profile/me` сейчас доступен только спортсмену.

### Тренировки

- `GET /api/trainings`
- `POST /api/trainings`
- `PUT /api/trainings/{training_id}`
- `DELETE /api/trainings/{training_id}`

Текущий Flutter-клиент уже использует полный цикл работы с тренировками:

- создание
- чтение
- обновление
- удаление

### Анализы

- `GET /api/analyses`
- `POST /api/analyses`
- `GET /api/analyses/{entry_id}`
- `PUT /api/analyses/{entry_id}`
- `DELETE /api/analyses/{entry_id}`

### Калории

- `GET /api/calories`
- `POST /api/calories`
- `GET /api/calories/{entry_id}`
- `PUT /api/calories/{entry_id}`
- `DELETE /api/calories/{entry_id}`

### Артериальное давление

- `GET /api/blood-pressure`
- `POST /api/blood-pressure`
- `GET /api/blood-pressure/{entry_id}`
- `PUT /api/blood-pressure/{entry_id}`
- `DELETE /api/blood-pressure/{entry_id}`

### Сон

- `GET /api/sleep`
- `POST /api/sleep`
- `GET /api/sleep/{entry_id}`
- `PUT /api/sleep/{entry_id}`
- `DELETE /api/sleep/{entry_id}`

### SpO2

- `GET /api/spo2`
- `POST /api/spo2`
- `GET /api/spo2/{entry_id}`
- `PUT /api/spo2/{entry_id}`
- `DELETE /api/spo2/{entry_id}`

### AI индекс физической формы

- `POST /api/ai/predict`
- `GET /api/ai/last`

`POST /api/ai/predict` доступен авторизованному пользователю и:

- для спортсмена использует его собственный `athlete_id`
- для тренера позволяет указать `athlete_id` только привязанного спортсмена

Поддерживаемое тело запроса:

```json
{
  "athlete_id": "optional-for-coach",
  "date_from": "2026-04-01",
  "date_to": "2026-04-05",
  "history_limit": 30
}
```

Пример ответа:

```json
{
  "id": "9d84c1f1-70b8-4e3b-a3f8-3e5cb0f0e2c9",
  "athlete_id": "4abef18f-95b7-4b09-a3d5-873ea0ea67d6",
  "date": "2026-04-05",
  "fitness_index": 84.2,
  "recommendations": "Сохранить текущую нагрузку и добавить контроль восстановления.",
  "created_at": "2026-04-05T12:30:00+00:00"
}
```

`GET /api/ai/last` возвращает последнюю сохраненную запись `FitnessScore`.

### Цикл

- `GET /api/cycle/settings`
- `PUT /api/cycle/settings`
- `GET /api/cycle/events?kind=...`
- `PUT /api/cycle/events`

Допустимые `kind`:

- `day`
- `excluded`
- `start`
- `end`

### Тренерские маршруты

- `GET /api/coach/athletes`
- `GET /api/coach/athletes/{athlete_id}`
- `POST /api/coach/athletes`
- `DELETE /api/coach/athletes/{athlete_id}`

Backend уже умеет:

- привязывать спортсмена к тренеру по email
- возвращать список привязанных спортсменов
- возвращать детальную карточку спортсмена
- включать в тренерскую сводку тренировки, анализы, калории, давление, сон и SpO2
- рассчитывать и сохранять AI-индекс физической формы через внешний ML-сервис

## Как backend используется клиентом сейчас

### Уже подключено во Flutter

- регистрация и вход
- чтение профиля через `/api/profile/me`
- обновление профиля спортсмена
- синхронизация тренировок
- синхронизация анализов
- синхронизация калорий
- синхронизация артериального давления
- синхронизация сна
- синхронизация SpO2
- синхронизация цикла
- запрос последнего AI fitness score
- ручной пересчет AI fitness score
- привязка спортсмена к тренеру по email
- загрузка списка спортсменов тренера и их детальной карточки

## Формат ошибок

Backend старается возвращать ошибки в виде:

```json
{"detail": "понятное текстовое сообщение"}
```

Это особенно важно для Flutter-клиента, который показывает `detail` напрямую в интерфейсе.

## Миграции

Alembic-модули находятся в `alembic/versions`.

По коду видно такие важные этапы развития схемы:

1. базовые пользователи, профили, тренировки и давление
2. калории и цикл
3. сон и SpO2
4. расширенные профили и связи тренер-спортсмен
5. `0007_fitness_scores` для AI-оценок физической формы

При создании новой тренировки, сна или давления backend может автоматически
добавлять фоновый пересчет fitness score через `FastAPI BackgroundTasks`.

## Безопасность

Сейчас backend делает важные вещи правильно:

- пароли хешируются через `bcrypt`
- длина пароля дополнительно ограничивается из-за ограничений `bcrypt`
- доступ к данным идёт через JWT
- спортсмен может читать только свои данные
- тренер может работать только с привязанными спортсменами

## Текущие сильные стороны backend

1. Серверная модель уже шире, чем текущий клиент.
2. Архитектура маршрутов простая и понятная.
3. Уже есть база для многопользовательской тренерской логики.
4. PostgreSQL-подход хорошо подходит для дальнейшего роста проекта.

## Что можно улучшить дальше

### Высокий приоритет

1. Добавить покрытие тестами auth, profile, coach links и health-маршрутов.
2. Сделать единый слой сервисов между route и ORM, чтобы уменьшить объём логики в эндпоинтах.
3. Добавить paging и фильтрацию для длинных списков тренировок и health-данных.
4. Добавить более явные audit-поля и soft-delete там, где это нужно.

### Средний приоритет

1. Добавить rate limit на auth-эндпоинты.
2. Подготовить Docker-конфигурацию для локального и демонстрационного запуска.
3. Добавить OpenAPI-примеры для сложных payload, особенно тренировок.
4. Добавить отдельные contract-tests между backend и Flutter-клиентом.

### Перспективные улучшения

1. Добавить агрегированные аналитические эндпоинты, чтобы разгрузить Flutter-клиент.
2. Поддержать импорт данных из носимых устройств через отдельный ingestion-слой.
3. Реализовать уведомления и фоновые задачи.
4. Добавить событийную историю изменений профиля и health-метрик.
