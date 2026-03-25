# Backend API (FastAPI + PostgreSQL)

## 1. Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy env template:

```powershell
copy .env.example .env
```

Update `DATABASE_URL`, `JWT_SECRET` and `CORS_ORIGINS` in `.env`.

For internet access:

- `DATABASE_URL` should point to your public/server PostgreSQL
- `CORS_ORIGINS` should be:
  - `*` for local/dev
  - or a comma-separated list of allowed origins in production
    Example:
    `https://app.example.com,http://localhost:3000`

## 2. Apply SQL schema

Preferred way:

```powershell
.venv\Scripts\alembic upgrade head
```

Legacy SQL scripts:

1. `../migrations/001_init.sql`
2. `../migrations/002_timescaledb.sql` (optional if TimescaleDB is installed)

## 3. Run server

```powershell
uvicorn app.main:app --reload --port 8000
```

For external devices, run behind a public host or reverse proxy and use:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Swagger UI:

- `http://127.0.0.1:8000/docs`

## 4. First endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/trainings`
- `POST /api/trainings`
- `GET /api/blood-pressure`
- `POST /api/blood-pressure`

`/api/trainings` and `/api/blood-pressure` require `Authorization: Bearer <token>`.

## 5. Public deploy

The backend is now prepared for public deployment.

Files added for deploy:

- `Dockerfile`
- `.dockerignore`
- `start.sh`
- `render.yaml`

### Render

Detailed Russian step-by-step guide:

- `RENDER_DEPLOY_RU.md`

1. Push `fitness_api/backend` to Git.
2. In Render create a new Blueprint or Web Service from this folder.
3. Set environment variables:
   - `DATABASE_URL`
   - `JWT_SECRET`
   - `CORS_ORIGINS`
4. Render will build the Docker image and run:
   - `python -m alembic upgrade head`
   - `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health check:

- `/api/health`

After deploy you will get a public URL like:

- `https://fitness-api.onrender.com`

Then run Flutter with:

```powershell
flutter run --dart-define=FITNESS_API_URL=https://fitness-api.onrender.com
```

### Railway / any Docker host

You can deploy the same backend using the included `Dockerfile`.
The container is self-starting through `start.sh` and binds to `0.0.0.0`.
