# Приложение. Ключевые фрагменты исходного кода

Ниже приведены наиболее важные фрагменты исходного кода проекта, которые можно включить в приложение к пояснительной записке. Для каждого фрагмента указаны его назначение и файл расположения.

## А.1. Регистрация и авторизация пользователя в backend

**Назначение:** данный фрагмент реализует регистрацию пользователя, создание профиля спортсмена или тренера, а также вход пользователя в систему с выдачей JWT-токена.

**Файл:** `backend/app/api/routes/auth.py`

```python
@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        ensure_bcrypt_password_limit(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    existing = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = AppUser(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "athlete":
        db.add(
            AthleteProfile(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                age=payload.age,
                gender=payload.gender,
                weight_kg=payload.weight_kg,
                height_cm=payload.height_cm,
                sport=payload.sport,
            )
        )
    else:
        db.add(
            CoachProfile(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
            )
        )

    db.commit()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, role=user.role)
```

---

## А.2. Проверка JWT-токена и пользовательской роли

**Назначение:** фрагмент реализует извлечение текущего пользователя по JWT-токену, а также разграничение доступа по ролям `athlete` и `coach`.

**Файл:** `backend/app/api/deps.py`

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AppUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        uuid_user_id = uuid.UUID(user_id)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    user = db.get(AppUser, uuid_user_id)
    if user is None:
        raise credentials_exception
    return user


def require_athlete(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "athlete":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete role required")
    return user


def require_coach(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "coach":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Coach role required")
    return user
```

---

## А.3. Сохранение тренировки и запуск фонового AI-пересчёта

**Назначение:** фрагмент реализует создание тренировочной записи спортсмена и немедленную постановку фоновой задачи на пересчёт аналитики.

**Файл:** `backend/app/api/routes/trainings.py`

```python
@router.post(
    "",
    response_model=TrainingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_training(
    payload: TrainingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Training:
    training = Training(
        athlete_id=user.id,
        title=payload.title,
        training_type=payload.training_type,
        date=payload.date,
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        distance_km=payload.distance_km,
        elevation_m=payload.elevation_m,
        avg_hr=payload.avg_hr,
        max_hr=payload.max_hr,
        calories=payload.calories,
        notes=payload.notes,
        sport=payload.sport,
        hr_zone=payload.hr_zone,
        hr_zone_minutes=payload.hr_zone_minutes,
        activity_types=payload.activity_types,
        exercises=payload.exercises,
        feeling_score=payload.feeling_score,
    )
    db.add(training)
    db.commit()
    db.refresh(training)
    background_tasks.add_task(enqueue_fitness_prediction, user.id)
    return training
```

---

## А.4. Агрегация истории спортсмена для ML-модуля

**Назначение:** данный фрагмент формирует единый `prediction payload`, содержащий профиль спортсмена, тренировки, сон, давление и SpO2 для передачи в интеллектуальный сервис.

**Файл:** `backend/app/services/fitness_ai_service.py`

```python
def build_prediction_payload(
    db: Session,
    *,
    athlete_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
    history_limit: int,
) -> dict[str, object]:
    trainings_stmt = (
        select(Training)
        .where(Training.athlete_id == athlete_id)
        .order_by(Training.date.desc())
        .limit(history_limit)
    )
    trainings_stmt = _apply_date_range(trainings_stmt, Training.date, date_from, date_to)
    trainings = list(db.scalars(trainings_stmt).all())

    sleep_stmt = (
        select(SleepEntry)
        .where(SleepEntry.athlete_id == athlete_id)
        .order_by(SleepEntry.end_ts.desc())
        .limit(history_limit)
    )
    sleep_stmt = _apply_datetime_range(sleep_stmt, SleepEntry.end_ts, date_from, date_to)
    sleep_entries = list(db.scalars(sleep_stmt).all())

    pressure_stmt = (
        select(BloodPressureEntry)
        .where(BloodPressureEntry.athlete_id == athlete_id)
        .order_by(BloodPressureEntry.ts.desc())
        .limit(history_limit)
    )
    pressure_stmt = _apply_datetime_range(pressure_stmt, BloodPressureEntry.ts, date_from, date_to)
    blood_pressures = list(db.scalars(pressure_stmt).all())

    spo2_stmt = (
        select(Spo2Entry)
        .where(Spo2Entry.athlete_id == athlete_id)
        .order_by(Spo2Entry.ts.desc())
        .limit(history_limit)
    )
    spo2_stmt = _apply_datetime_range(spo2_stmt, Spo2Entry.ts, date_from, date_to)
    spo2_entries = list(db.scalars(spo2_stmt).all())

    return {
        "athlete_id": str(athlete_id),
        "date_from": date_from.isoformat() if date_from is not None else None,
        "date_to": date_to.isoformat() if date_to is not None else None,
        "history_limit": history_limit,
        "profile": _load_profile_context(db, athlete_id),
        "trainings": _serialize_trainings(trainings),
        "sleep": _serialize_sleep(sleep_entries),
        "blood_pressure": _serialize_blood_pressure(blood_pressures),
        "spo2": _serialize_spo2(spo2_entries),
    }
```

---

## А.5. Вызов ML-сервиса и сохранение результата аналитики

**Назначение:** фрагмент показывает, как backend вызывает интеллектуальный модуль и сохраняет рассчитанный результат в таблицу `fitness_scores`.

**Файл:** `backend/app/services/fitness_ai_service.py`

```python
async def predict_and_store_fitness_score(
    db: Session,
    *,
    athlete_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    history_limit: int = 30,
) -> FitnessScore:
    payload = build_prediction_payload(
        db,
        athlete_id=athlete_id,
        date_from=date_from,
        date_to=date_to,
        history_limit=history_limit,
    )
    prediction = await _call_ai_service(payload)
    score = FitnessScore(
        athlete_id=athlete_id,
        fitness_index=prediction.fitness_index,
        fatigue_risk=prediction.fatigue_risk,
        trend=prediction.trend,
        recommendations=prediction.recommendations,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score
```

---

## А.6. Предобработка данных в интеллектуальном модуле

**Назначение:** фрагмент демонстрирует формирование производных признаков `training_load`, `recovery_signal`, `cardio_signal`, а также построение итогового набора табличных признаков для ML-моделей.

**Файл:** `ml_service/services/preprocessing.py`

```python
        training_load = _clamp(
            duration_minutes * 0.6
            + calories * 0.04
            + max(0.0, avg_hr - 110.0) * 0.35
            + max(0.0, max_hr - 150.0) * 0.10
        )
        recovery_signal = _clamp(
            20.0
            + sleep_hours * 7.0
            + feeling_score * 5.0
            + max(0.0, spo2 - 94.0) * 6.0
            - max(0.0, systolic - 120.0) * 0.6
            - max(0.0, diastolic - 80.0) * 0.9
        )
        cardio_signal = _clamp(
            15.0
            + duration_minutes * 0.35
            + max(0.0, 155.0 - avg_hr) * 0.45
            + max(0.0, spo2 - 92.0) * 4.0
            + max(0.0, 60.0 - abs(duration_minutes - 60.0)) * 0.15
        )

    recent_window = min(settings.short_horizon_days, effective_window)
    previous_window = min(recent_window, max(1, effective_window - recent_window))
    recent_load = _mean(daily_training_loads[-recent_window:])
    chronic_load = _mean(daily_training_loads)
    previous_load = _mean(daily_training_loads[-(recent_window + previous_window):-recent_window]) if effective_window > recent_window else chronic_load

    avg_sleep_hours = _mean(daily_sleep_hours, default=7.0)
    sleep_consistency = _clamp(100.0 - _std(daily_sleep_hours or [7.0]) * 18.0)
    training_consistency = _clamp(training_days / effective_window * 100.0)
    acute_chronic_ratio = recent_load / chronic_load if chronic_load > 0 else (1.0 if recent_load == 0 else 1.35)

    tabular_row = [
        recent_load,
        chronic_load,
        acute_chronic_ratio,
        training_consistency,
        avg_sleep_hours,
        sleep_consistency,
        avg_avg_hr,
        avg_max_hr,
        avg_spo2,
        avg_systolic,
        avg_diastolic,
        avg_feeling_score,
        float(profile.age or 0.0),
        float(profile.weight_kg or 0.0),
        float(profile.height_cm or 0.0),
    ]
```

---

## А.7. Расчёт индекса физической формы и риска утомления

**Назначение:** данный фрагмент является центральной частью интеллектуального модуля и показывает, как вычисляются `fitness_index`, `fatigue_risk` и `trend`.

**Файл:** `ml_service/services/inference.py`

```python
def run_prediction_pipeline(
    *,
    prepared: PreparedInferenceInput,
    models: ModelArtifacts,
    settings: MLServiceSettings,
) -> PredictionResult:
    scaled_features = _apply_scaler(models.scaler, prepared.tabular_features)
    sequence_batch = _wrap_sequence_batch(prepared.sequence_matrix)

    load_score = _clamp(
        _predict_scalar(
            models.load_model,
            scaled_features,
            fallback=prepared.metrics["recent_load"],
            label="load_model",
        )
    )
    recovery_score = _clamp(
        _predict_scalar(
            models.recovery_model,
            scaled_features,
            fallback=prepared.metrics["recent_recovery"],
            label="recovery_model",
        )
    )
    cardio_score = _clamp(
        _predict_scalar(
            models.cardio_model,
            scaled_features,
            fallback=prepared.metrics["recent_cardio"],
            label="cardio_model",
        )
    )

    trend = _resolve_trend(prepared, patchtst_score=patchtst_score, timesfm_score=timesfm_score)
    fitness_index = _clamp(
        0.22 * load_score
        + 0.26 * recovery_score
        + 0.18 * cardio_score
        + 0.17 * patchtst_score
        + 0.17 * timesfm_score
        + _trend_adjustment(trend),
        settings.fitness_index_min,
        settings.fitness_index_max,
    )

    load_strain = max(0.0, (prepared.metrics["acute_chronic_ratio"] - 1.0) * 55.0)
    load_delta = max(0.0, prepared.metrics["recent_load"] - prepared.metrics["previous_load"])
    fatigue_risk = _clamp(
        0.55 * (100.0 - recovery_score)
        + 0.25 * load_strain
        + 0.20 * load_delta
        + (8.0 if trend == "down" else 0.0),
        0.0,
        100.0,
    )
```

---

## А.8. Offline-first авторизация и восстановление пользовательской сессии в клиентском приложении

**Назначение:** фрагмент показывает комбинированный алгоритм авторизации во Flutter-приложении: сначала через backend, затем через “провижининг” локального профиля на сервер и, в крайнем случае, через локальный вход.

**Файл:** `fitness_app/lib/userState/app_session_controller.dart`

```dart
Future<bool> authenticateUser(
  UserRole role, {
  required String email,
  required String password,
}) async {
  try {
    if (await _authenticateWithBackend(email: email, password: password)) {
      return true;
    }

    if (await _provisionBackendUserFromLocalProfile(
      role,
      email: email,
      password: password,
    )) {
      final migrated = await _authenticateWithBackend(
        email: email,
        password: password,
      );
      if (migrated) {
        return true;
      }
    }

    final localSuccess = await _authenticateLocally(
      role,
      email: email,
      password: password,
    );
    if (localSuccess) {
      await syncMeta.markSuccess('auth');
      return true;
    }
```

---

## А.9. Кэширование профиля и тренировок на клиенте

**Назначение:** данный фрагмент демонстрирует локальное кэширование данных пользователя и тренировок в `SharedPreferences`, что обеспечивает offline-first поведение мобильного приложения.

**Файл:** `fitness_app/lib/services/storage_service.dart`

```dart
Future<void> saveAthleteProfile(AthleteProfile? profile) async {
  final prefs = await SharedPreferences.getInstance();
  if (profile == null) {
    await prefs.remove(_keyAthleteProfile);
    return;
  }
  final json = {
    'firstName': profile.firstName,
    'lastName': profile.lastName,
    'email': profile.email,
    'password': profile.password,
    'age': profile.age,
    'gender': profile.gender,
    'weightKg': profile.weightKg,
    'heightCm': profile.heightCm,
    'sport': profile.sport,
    'createdAt': profile.createdAt.toIso8601String(),
  };
  await prefs.setString(_keyAthleteProfile, jsonEncode(json));
}

Future<void> saveTrainings(List<TrainingEntry> trainings) async {
  final prefs = await SharedPreferences.getInstance();
  final jsonList = trainings
      .map(
        (t) => {
          'backendId': t.backendId,
          'title': t.title,
          'trainingType': t.trainingType,
          'date': t.date.toIso8601String(),
          'durationMinutes': t.durationMinutes,
          'sport': t.sport,
          'activityTypes': t.activityTypes,
          'hrZoneMinutes': t.hrZoneMinutes,
          'maxHr': t.maxHr,
          'avgHr': t.avgHr,
          'calories': t.calories,
          'notes': t.notes,
          'hrZone': t.hrZone,
          'feelingScore': t.feelingScore,
          'distanceKm': t.distanceKm,
          'startTime': t.startTime?.toIso8601String(),
        },
      )
      .toList();
  await prefs.setString(_keyTrainings, jsonEncode(jsonList));
}
```

---

## А.10. Локальная очередь синхронизации тренировок

**Назначение:** фрагмент реализует очередь операций синхронизации, которая временно сохраняет пользовательские изменения при отсутствии backend и отправляет их позднее.

**Файл:** `fitness_app/lib/services/training_sync_queue_service.dart`

```dart
Future<void> enqueue({
  required String operation,
  required TrainingEntry entry,
}) async {
  await enqueueRaw(operation: operation, payload: _trainingToJson(entry));
}

Future<void> enqueueRaw({
  required String operation,
  required Map<String, dynamic> payload,
}) async {
  final queue = await loadQueue();
  queue.add({
    'operation': operation,
    'entry': payload,
    'createdAt': DateTime.now().toIso8601String(),
  });
  await saveQueue(queue);
}

Future<List<Map<String, dynamic>>> loadQueue() async {
  final prefs = await SharedPreferences.getInstance();
  final jsonStr = prefs.getString(_keyTrainingSyncQueue);
  if (jsonStr == null) return [];
  try {
    final decoded = jsonDecode(jsonStr) as List<dynamic>;
    return decoded
        .whereType<Map<String, dynamic>>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  } catch (_) {
    return [];
  }
}
```

---

## Рекомендации по включению в пояснительную записку

Если нужно сделать приложение компактным, в первую очередь рекомендуется включить фрагменты:

1. **А.1** — регистрация и авторизация пользователя;
2. **А.2** — проверка JWT и ролей;
3. **А.3** — сохранение тренировки и запуск AI;
4. **А.4** — агрегация истории спортсмена;
5. **А.5** — вызов ML-сервиса и сохранение результата;
6. **А.6** — предобработка данных;
7. **А.7** — расчёт `fitness_index` и `fatigue_risk`;
8. **А.8** — offline-first авторизация во Flutter;
9. **А.9** — кэширование локальных данных.

Именно эти фрагменты лучше всего показывают архитектурную и прикладную уникальность проекта.
