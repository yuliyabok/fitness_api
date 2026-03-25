import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.analysis import AnalysisEntry
from app.models.blood_pressure import BloodPressureEntry
from app.models.calorie import CalorieEntry
from app.models.cycle import CycleEvent, CycleSettings
from app.models.training import Training
from app.models.user import AppUser, AthleteProfile, CoachProfile


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object (key-value map)")
    return data


def _get_pref(data: dict[str, Any], key: str) -> Any:
    if key in data:
        return data[key]
    fkey = f"flutter.{key}"
    return data.get(fkey)


def _decode_maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        s = value.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return json.loads(s)
            except Exception:
                return value
    return value


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _parse_date(v: Any) -> date | None:
    dt = _parse_dt(v)
    return dt.date() if dt else None


def _parse_time(v: Any):
    dt = _parse_dt(v)
    return dt.time() if dt else None


def _ensure_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: str,
    first_name: str,
    last_name: str,
) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email.lower()))
    if user is None:
        user = AppUser(email=email.lower(), password_hash=hash_password(password), role=role)
        db.add(user)
        db.flush()
    
    if role == "athlete":
        profile = db.get(AthleteProfile, user.id)
        if profile is None:
            db.add(AthleteProfile(user_id=user.id, first_name=first_name, last_name=last_name))
    else:
        profile = db.get(CoachProfile, user.id)
        if profile is None:
            db.add(CoachProfile(user_id=user.id, first_name=first_name, last_name=last_name))

    return user


def _upsert_training(db: Session, athlete_id, item: dict[str, Any]) -> None:
    t_date = _parse_date(item.get("date"))
    if t_date is None:
        return
    title = (item.get("title") or "Training").strip()
    duration = int(item.get("durationMinutes") or 0)

    exists = db.scalar(
        select(Training).where(
            Training.athlete_id == athlete_id,
            Training.title == title,
            Training.date == t_date,
            Training.duration_minutes == duration,
        )
    )
    if exists:
        return

    db.add(
        Training(
            athlete_id=athlete_id,
            title=title,
            training_type=item.get("trainingType") or "Unknown",
            date=t_date,
            start_time=_parse_time(item.get("startTime")),
            duration_minutes=duration,
            distance_km=float(item.get("distanceKm")) if item.get("distanceKm") is not None else None,
            elevation_m=int(item.get("elevationGainM")) if item.get("elevationGainM") is not None else None,
            avg_hr=int(item.get("avgHr")) if item.get("avgHr") is not None else None,
            max_hr=int(item.get("maxHr")) if item.get("maxHr") is not None else None,
            calories=int(item.get("calories")) if item.get("calories") is not None else None,
            notes=item.get("notes"),
            sport=item.get("sport"),
            hr_zone=item.get("hrZone"),
            hr_zone_minutes=item.get("hrZoneMinutes") if isinstance(item.get("hrZoneMinutes"), dict) else None,
            exercises=item.get("exercises") if isinstance(item.get("exercises"), list) else None,
            feeling_score=int(item.get("feelingScore")) if item.get("feelingScore") is not None else None,
            activity_types=item.get("activityTypes") if isinstance(item.get("activityTypes"), list) else None,
        )
    )


def _upsert_analysis(db: Session, athlete_id, item: dict[str, Any]) -> None:
    d = _parse_date(item.get("date"))
    if d is None:
        return
    title = item.get("title") or "Analysis"
    exists = db.scalar(
        select(AnalysisEntry).where(
            AnalysisEntry.athlete_id == athlete_id,
            AnalysisEntry.date == d,
            AnalysisEntry.title == title,
            AnalysisEntry.value == item.get("value"),
        )
    )
    if exists:
        return
    db.add(
        AnalysisEntry(
            athlete_id=athlete_id,
            date=d,
            title=title,
            value=item.get("value"),
            notes=item.get("notes"),
        )
    )


def _upsert_calorie(db: Session, athlete_id, item: dict[str, Any]) -> None:
    d = _parse_date(item.get("date"))
    calories = item.get("calories")
    if d is None or calories is None:
        return
    exists = db.scalar(
        select(CalorieEntry).where(
            CalorieEntry.athlete_id == athlete_id,
            CalorieEntry.date == d,
            CalorieEntry.calories == int(calories),
        )
    )
    if exists:
        return
    db.add(CalorieEntry(athlete_id=athlete_id, date=d, calories=int(calories), notes=item.get("notes")))


def _upsert_bp(db: Session, athlete_id, item: dict[str, Any]) -> None:
    ts = _parse_dt(item.get("date") or item.get("ts"))
    if ts is None:
        return
    systolic = item.get("systolic")
    diastolic = item.get("diastolic")
    if systolic is None or diastolic is None:
        return
    exists = db.scalar(
        select(BloodPressureEntry).where(
            BloodPressureEntry.athlete_id == athlete_id,
            BloodPressureEntry.ts == ts,
            BloodPressureEntry.is_morning == bool(item.get("isMorning", item.get("is_morning", True))),
        )
    )
    if exists:
        return
    db.add(
        BloodPressureEntry(
            athlete_id=athlete_id,
            ts=ts,
            is_morning=bool(item.get("isMorning", item.get("is_morning", True))),
            systolic=int(systolic),
            diastolic=int(diastolic),
        )
    )


def _upsert_cycle_data(db: Session, athlete_id, data: dict[str, Any]) -> None:
    def add_dates(kind: str, key: str):
        dates = _decode_maybe_json(_get_pref(data, key)) or []
        if not isinstance(dates, list):
            return
        for d in dates:
            day = _parse_date(d)
            if day is None:
                continue
            exists = db.scalar(
                select(CycleEvent).where(
                    CycleEvent.athlete_id == athlete_id,
                    CycleEvent.date == day,
                    CycleEvent.kind == kind,
                )
            )
            if not exists:
                db.add(CycleEvent(athlete_id=athlete_id, date=day, kind=kind))

    add_dates("day", "cycle_dates")
    add_dates("excluded", "cycle_excluded_dates")
    add_dates("start", "cycle_start_dates")
    add_dates("end", "cycle_end_dates")

    cycle_len = _get_pref(data, "cycle_length_days")
    period_len = _get_pref(data, "period_length_days")
    if cycle_len is not None or period_len is not None:
        row = db.get(CycleSettings, athlete_id)
        if row is None:
            row = CycleSettings(athlete_id=athlete_id)
            db.add(row)
        if cycle_len is not None:
            row.cycle_length_days = int(cycle_len)
        if period_len is not None:
            row.period_length_days = int(period_len)


def _as_list_pref(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = _decode_maybe_json(_get_pref(data, key))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def import_legacy(input_path: Path, dry_run: bool) -> None:
    data = _load_json(input_path)

    with SessionLocal() as db:
        # Current athlete profile branch
        athlete_json = _decode_maybe_json(_get_pref(data, "athlete_profile"))
        if isinstance(athlete_json, dict):
            user = _ensure_user(
                db,
                email=athlete_json.get("email", "unknown-athlete@example.local"),
                password=athlete_json.get("password", "changeme"),
                role="athlete",
                first_name=athlete_json.get("firstName", "Athlete"),
                last_name=athlete_json.get("lastName", "User"),
            )
            athlete_id = user.id

            for t in _as_list_pref(data, "trainings"):
                _upsert_training(db, athlete_id, t)
            for bp in _as_list_pref(data, "blood_pressures"):
                _upsert_bp(db, athlete_id, bp)
            for a in _as_list_pref(data, "analyses"):
                _upsert_analysis(db, athlete_id, a)
            for c in _as_list_pref(data, "calories"):
                _upsert_calorie(db, athlete_id, c)
            _upsert_cycle_data(db, athlete_id, data)

        # Coach profile branch
        coach_json = _decode_maybe_json(_get_pref(data, "coach_profile"))
        if isinstance(coach_json, dict):
            _ensure_user(
                db,
                email=coach_json.get("email", "unknown-coach@example.local"),
                password=coach_json.get("password", "changeme"),
                role="coach",
                first_name=coach_json.get("firstName", "Coach"),
                last_name=coach_json.get("lastName", "User"),
            )

        # Athletes list under coach
        athletes = _as_list_pref(data, "athletes")
        for rec in athletes:
            p = rec.get("profile") if isinstance(rec.get("profile"), dict) else None
            if not p:
                continue
            user = _ensure_user(
                db,
                email=p.get("email", "unknown-athlete@example.local"),
                password=p.get("password", "changeme"),
                role="athlete",
                first_name=p.get("firstName", "Athlete"),
                last_name=p.get("lastName", "User"),
            )
            athlete_id = user.id
            for t in (rec.get("trainings") or []):
                if isinstance(t, dict):
                    _upsert_training(db, athlete_id, t)
            for a in (rec.get("analyses") or []):
                if isinstance(a, dict):
                    _upsert_analysis(db, athlete_id, a)
            for c in (rec.get("calories") or []):
                if isinstance(c, dict):
                    _upsert_calorie(db, athlete_id, c)

        if dry_run:
            db.rollback()
            print("Dry run complete. No changes committed.")
        else:
            db.commit()
            print("Legacy data import complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy local app data into PostgreSQL")
    parser.add_argument("--input", required=True, help="Path to JSON with SharedPreferences key-values")
    parser.add_argument("--dry-run", action="store_true", help="Validate import without commit")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    import_legacy(input_path=input_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
