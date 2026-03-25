# Render deploy for this monorepo

## 1. Push the project to GitHub

1. Commit the repository.
2. Push it to GitHub.
3. Make sure the backend folder is present at:
   - `fitness_api/backend`

Render will use this folder as the Root Directory for the web service.

## 2. Create PostgreSQL in Render

1. Open Render dashboard.
2. Click `New +` -> `PostgreSQL`.
3. Set:
   - Name: `fitness-db`
   - Database: `fitness_app`
   - User: leave auto-generated or set your own
   - Region: choose the same region where the backend will run
4. Create the database.
5. After creation, open the database page and copy:
   - `Internal Database URL` if the backend is in Render too
   - or `External Database URL` if you need outside access

For this project, use the `Internal Database URL` in the backend service.

## 3. Create the FastAPI web service

1. In Render click `New +` -> `Web Service`.
2. Connect your GitHub repository.
3. Select the repository.
4. Configure the service exactly like this:
   - Name: `fitness-api`
   - Region: same as PostgreSQL
   - Branch: your main branch
   - Root Directory: `fitness_api/backend`
   - Runtime: `Docker`
   - Plan: your choice

Do not point Render to the repository root. The backend lives in `fitness_api/backend`.

## 4. Set environment variables

In the Render web service, open `Environment` and add:

- `DATABASE_URL`
  - value: paste the Render PostgreSQL `Internal Database URL`
- `JWT_SECRET`
  - value: generate a long random secret
- `JWT_ALGORITHM`
  - value: `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
  - value: `120`
- `CORS_ORIGINS`
  - for initial testing: `*`
  - later restrict it if needed

## 5. Deploy settings

The project already contains:

- `Dockerfile`
- `start.sh`
- `.dockerignore`

`start.sh` does two things on each deploy:

1. runs migrations:
   - `python -m alembic upgrade head`
2. starts FastAPI:
   - `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

You do not need to enter a custom Start Command in Render.

## 6. First deploy

1. Click `Create Web Service`.
2. Wait for the build to finish.
3. Open the deployed service URL.
4. Check health endpoint:
   - `https://YOUR-RENDER-URL/api/health`

If this endpoint responds successfully, the backend is publicly reachable.

## 7. Verify database migrations

In Render logs you should see Alembic applying migrations before Uvicorn starts.
If migrations fail, check:

- `DATABASE_URL`
- whether PostgreSQL is in the same region
- whether the database is running

## 8. Point Flutter to the public backend

Run the client with the public API URL:

```powershell
flutter run --dart-define=FITNESS_API_URL=https://YOUR-RENDER-URL
```

For release builds use the same `--dart-define` with your build command.

## 9. Test the real multi-device scenario

Test in this order:

1. Register athlete on device A
2. Log in with the same athlete on device B
3. Register coach on device C
4. Link athlete by email from the coach account
5. Add athlete data on one device
6. Open the same athlete on another device and confirm data is loaded from backend

## 10. Production notes

1. Use `https`, not `http`
2. Replace `CORS_ORIGINS=*` with a restricted list later
3. Rotate `JWT_SECRET` only with care, because old tokens become invalid
4. Monitor free-tier cold starts if you use the free Render plan
