# Fitness API Backend

FastAPI backend для фитнес-приложения.

## Назначение

Backend отвечает за:

- регистрацию и вход пользователей
- выпуск JWT токенов
- хранение профилей спортсменов и тренеров
- хранение тренировок
- хранение анализов
- хранение калорий
- хранение артериального давления
- хранение данных сна
- хранение SpO2
- хранение данных цикла
- связь тренер -> спортсмен

## Технологии

- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL
- `python-jose` для JWT
- `bcrypt` для хеширования паролей

## Точка входа

Файл: `app/main.py`

Backend:

1. создаёт `FastAPI` приложение
2. настраивает CORS
3. подключает общий роутер `/api`

## Конфигурация

Файл: `app/core/config.py`

Обязательные переменные окружения:

- `DATABASE_URL`
- `JWT_SECRET`

Необязательные:

- `CORS_ORIGINS`
- `JWT_ALGORITHM` по умолчанию `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES` по умолчанию `120`

`.env` поддерживается через `pydantic-settings`.

## Локальный запуск

```bash
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Или через стартовый скрипт:

```bash
./start.sh
```

Скрипт сначала применяет миграции, потом запускает `uvicorn`.

## Аутентификация

### Регистрация

`POST /api/auth/register`

Создаёт:

- запись в `app_users`
- профиль спортсмена или тренера

Входные данные:

- email
- password
- role: `athlete` или `coach`
- first_name
- last_name
- для спортсмена также могут передаваться:
  `age`, `gender`, `weight_kg`, `height_cm`, `sport`

### Логин

`POST /api/auth/login`

Проверяет email и пароль, затем возвращает:

- `access_token`
- `token_type = bearer`

### JWT

Токен содержит:

- `sub` - UUID пользователя
- `exp` - срок истечения

Зависимости авторизации:

- `get_current_user`
- `require_athlete`
- `require_coach`

## Структура данных

### Пользователи

Таблицы:

- `app_users`
- `athlete_profiles`
- `coach_profiles`
- `coach_athlete_links`

### Health и activity

Таблицы:

- `trainings`
- `analysis_entries`
- `calorie_entries`
- `blood_pressure_entries`
- `sleep_entries`
- `spo2_entries`
- `cycle_events`
- `cycle_settings`

## API маршруты

### Служебный маршрут

- `GET /api/health` - проверка доступности сервиса

### Профиль

- `GET /api/profile/me`
- `PUT /api/profile/me`

`PUT` разрешён только для спортсмена.

### Тренировки

- `GET /api/trainings`
- `POST /api/trainings`
- `PUT /api/trainings/{training_id}`
- `DELETE /api/trainings/{training_id}`

Особенности модели тренировки:

- дата и время старта
- длительность
- дистанция
- набор высоты
- средний и максимальный пульс
- калории
- зона ЧСС
- минуты по зонам ЧСС
- типы активности
- упражнения в JSONB
- субъективная оценка самочувствия

### Анализы

- `GET /api/analyses`
- `POST /api/analyses`

### Калории

- `GET /api/calories`
- `POST /api/calories`

### Давление

- `GET /api/blood-pressure`
- `POST /api/blood-pressure`

### Сон

- `GET /api/sleep`
- `POST /api/sleep`

### SpO2

- `GET /api/spo2`
- `POST /api/spo2`

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

Backend умеет:

- привязывать спортсмена к тренеру по email
- выдавать список привязанных спортсменов
- выдавать подробную сводку по спортсмену:
  тренировки, анализы, калории, давление, сон, SpO2

## База данных и миграции

Alembic миграции находятся в `alembic/versions`.

Основные этапы развития схемы:

1. `0001_init`
   создаёт пользователей, профили, тренировки и давление
2. `0002_calories_cycle`
   добавляет калории и цикл
3. `0004_sleep_spo2`
   добавляет сон и SpO2
4. `0005_profiles_and_coach_links`
   расширяет профиль спортсмена и добавляет связь тренер-спортсмен

## Правила безопасности

- пароли хешируются через `bcrypt`
- длина пароля дополнительно ограничивается до 72 байт из-за особенностей `bcrypt`
- доступ к данным идёт по JWT
- спортсмен видит только свои данные
- тренер видит только привязанных к нему спортсменов

## Что уже поддержано, но не полностью используется клиентом

Backend уже умеет больше, чем текущий Flutter-клиент использует в локальном режиме:

- обновление и удаление тренировок
- маршруты сна
- маршруты SpO2
- тренерские связи через backend
- редактирование профиля спортсмена

Это важно учитывать при дальнейшем развитии клиента: часть серверной базы уже готова и её можно подключать без переработки схемы.
