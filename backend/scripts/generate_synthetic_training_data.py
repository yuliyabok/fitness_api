from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.analysis import AnalysisEntry
from app.models.blood_pressure import BloodPressureEntry
from app.models.sleep import SleepEntry
from app.models.spo2 import Spo2Entry
from app.models.training import Training
from app.models.user import AppUser, AthleteProfile

PATTERNS = ("improving", "stable", "overloaded", "poor_sleep", "inconsistent", "returning")
SPORTS = ("Running", "Cycling", "Swimming", "Strength", "Triathlon")


@dataclass(slots=True)
class AthleteSeedProfile:
    email: str
    first_name: str
    last_name: str
    age: int
    weight_kg: float
    height_cm: float
    sport: str
    pattern: str


def main() -> None:
    args = parse_args()
    end_date = args.end_date or (date.today() - timedelta(days=1))
    start_date = end_date - timedelta(days=args.days - 1)

    inserted_counts = {
        "users": 0,
        "profiles": 0,
        "trainings": 0,
        "sleep_entries": 0,
        "blood_pressure_entries": 0,
        "spo2_entries": 0,
        "analysis_entries": 0,
    }

    with SessionLocal() as db:
        for athlete_index in range(args.start_index, args.start_index + args.athletes):
            profile = build_athlete_profile(
                athlete_index=athlete_index,
                email_prefix=args.email_prefix,
                seed=args.seed,
            )
            athlete_id, created_user, created_profile = ensure_athlete(db, profile=profile, password=args.password)
            inserted_counts["users"] += int(created_user)
            inserted_counts["profiles"] += int(created_profile)

            existing_keys = load_existing_keys(db, athlete_id=athlete_id)
            generated = seed_athlete_history(
                db=db,
                athlete_id=athlete_id,
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                seed=args.seed,
                existing_keys=existing_keys,
            )
            for key, value in generated.items():
                inserted_counts[key] += value

            if args.dry_run:
                db.rollback()
            else:
                db.commit()

    print(
        "Synthetic seed completed:",
        ", ".join(f"{key}={value}" for key, value in inserted_counts.items()),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic synthetic athlete data in PostgreSQL so the ML dataset "
            "pipeline can be trained and validated before real wearable/import data arrives."
        )
    )
    parser.add_argument("--athletes", type=int, default=24, help="Number of synthetic athletes to generate.")
    parser.add_argument("--days", type=int, default=120, help="Number of history days per athlete.")
    parser.add_argument("--seed", type=int, default=20260412, help="Global random seed.")
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting athlete index. Useful if you want to append more synthetic athletes later.",
    )
    parser.add_argument(
        "--email-prefix",
        default="synthetic.ml",
        help="Email prefix for generated accounts. Final emails look like prefix+001@example.com.",
    )
    parser.add_argument(
        "--password",
        default="synthetic-pass",
        help="Password assigned to generated athlete accounts.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Last date to generate. Defaults to yesterday.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate rows but rollback instead of committing.",
    )
    return parser.parse_args()


def build_athlete_profile(*, athlete_index: int, email_prefix: str, seed: int) -> AthleteSeedProfile:
    rng = random.Random(seed + athlete_index * 1000)
    sport = SPORTS[(athlete_index - 1) % len(SPORTS)]
    pattern = PATTERNS[(athlete_index - 1) % len(PATTERNS)]
    first_name = f"Synthetic{athlete_index:03d}"
    last_name = pattern.title().replace("_", "")
    email = f"{email_prefix}+{athlete_index:03d}@example.com"
    age = rng.randint(20, 44)
    height_cm = round(rng.uniform(160.0, 192.0), 1)
    weight_kg = round(rng.uniform(56.0, 92.0), 1)
    return AthleteSeedProfile(
        email=email.lower(),
        first_name=first_name,
        last_name=last_name,
        age=age,
        weight_kg=weight_kg,
        height_cm=height_cm,
        sport=sport,
        pattern=pattern,
    )


def ensure_athlete(db: Session, *, profile: AthleteSeedProfile, password: str) -> tuple[object, bool, bool]:
    user = db.scalar(select(AppUser).where(AppUser.email == profile.email))
    created_user = False
    created_profile = False
    if user is None:
        user = AppUser(
            email=profile.email,
            password_hash=hash_password(password),
            role="athlete",
        )
        db.add(user)
        db.flush()
        created_user = True

    athlete_profile = db.get(AthleteProfile, user.id)
    if athlete_profile is None:
        athlete_profile = AthleteProfile(
            user_id=user.id,
            first_name=profile.first_name,
            last_name=profile.last_name,
            age=profile.age,
            weight_kg=profile.weight_kg,
            height_cm=profile.height_cm,
            sport=profile.sport,
            gender="synthetic",
        )
        db.add(athlete_profile)
        db.flush()
        created_profile = True
    else:
        athlete_profile.first_name = profile.first_name
        athlete_profile.last_name = profile.last_name
        athlete_profile.age = profile.age
        athlete_profile.weight_kg = profile.weight_kg
        athlete_profile.height_cm = profile.height_cm
        athlete_profile.sport = profile.sport

    return user.id, created_user, created_profile


def load_existing_keys(db: Session, *, athlete_id: object) -> dict[str, set[tuple]]:
    trainings = {
        (row.date, row.title, row.duration_minutes or 0)
        for row in db.execute(
            select(Training).where(Training.athlete_id == athlete_id)
        ).scalars()
    }
    sleep_entries = {
        (row.start_ts, row.end_ts)
        for row in db.execute(
            select(SleepEntry).where(SleepEntry.athlete_id == athlete_id)
        ).scalars()
    }
    pressure_entries = {
        (row.ts, row.is_morning)
        for row in db.execute(
            select(BloodPressureEntry).where(BloodPressureEntry.athlete_id == athlete_id)
        ).scalars()
    }
    spo2_entries = {
        row.ts
        for row in db.execute(
            select(Spo2Entry).where(Spo2Entry.athlete_id == athlete_id)
        ).scalars()
    }
    analysis_entries = {
        (row.date, row.title)
        for row in db.execute(
            select(AnalysisEntry).where(AnalysisEntry.athlete_id == athlete_id)
        ).scalars()
    }
    return {
        "trainings": trainings,
        "sleep_entries": sleep_entries,
        "blood_pressure_entries": pressure_entries,
        "spo2_entries": spo2_entries,
        "analysis_entries": analysis_entries,
    }


def seed_athlete_history(
    *,
    db: Session,
    athlete_id: object,
    profile: AthleteSeedProfile,
    start_date: date,
    end_date: date,
    seed: int,
    existing_keys: dict[str, set[tuple]],
) -> dict[str, int]:
    rng = random.Random(seed + hash(profile.email))
    inserted = {
        "trainings": 0,
        "sleep_entries": 0,
        "blood_pressure_entries": 0,
        "spo2_entries": 0,
        "analysis_entries": 0,
    }

    day_count = (end_date - start_date).days + 1
    for offset in range(day_count):
        current_date = start_date + timedelta(days=offset)
        progress = offset / max(1, day_count - 1)
        snapshot = generate_daily_snapshot(
            rng=rng,
            profile=profile,
            current_date=current_date,
            progress=progress,
        )

        if snapshot["training"] is not None:
            training_key = (
                current_date,
                snapshot["training"]["title"],
                snapshot["training"]["duration_minutes"],
            )
            if training_key not in existing_keys["trainings"]:
                db.add(
                    Training(
                        athlete_id=athlete_id,
                        title=snapshot["training"]["title"],
                        training_type=snapshot["training"]["training_type"],
                        activity_types=[profile.sport.lower()],
                        sport=profile.sport,
                        date=current_date,
                        start_time=snapshot["training"]["start_time"],
                        duration_minutes=snapshot["training"]["duration_minutes"],
                        distance_km=snapshot["training"]["distance_km"],
                        elevation_m=snapshot["training"]["elevation_m"],
                        avg_hr=snapshot["training"]["avg_hr"],
                        max_hr=snapshot["training"]["max_hr"],
                        calories=snapshot["training"]["calories"],
                        hr_zone=snapshot["training"]["hr_zone"],
                        hr_zone_minutes=snapshot["training"]["hr_zone_minutes"],
                        exercises=snapshot["training"]["exercises"],
                        feeling_score=snapshot["training"]["feeling_score"],
                        notes=f"synthetic pattern={profile.pattern}",
                    )
                )
                existing_keys["trainings"].add(training_key)
                inserted["trainings"] += 1

        sleep_key = (snapshot["sleep"]["start_ts"], snapshot["sleep"]["end_ts"])
        if sleep_key not in existing_keys["sleep_entries"]:
            db.add(
                SleepEntry(
                    athlete_id=athlete_id,
                    start_ts=snapshot["sleep"]["start_ts"],
                    end_ts=snapshot["sleep"]["end_ts"],
                    deep_minutes=snapshot["sleep"]["deep_minutes"],
                    light_minutes=snapshot["sleep"]["light_minutes"],
                    rem_minutes=snapshot["sleep"]["rem_minutes"],
                    source="synthetic",
                )
            )
            existing_keys["sleep_entries"].add(sleep_key)
            inserted["sleep_entries"] += 1

        bp_key = (snapshot["bp"]["ts"], snapshot["bp"]["is_morning"])
        if bp_key not in existing_keys["blood_pressure_entries"]:
            db.add(
                BloodPressureEntry(
                    athlete_id=athlete_id,
                    ts=snapshot["bp"]["ts"],
                    is_morning=snapshot["bp"]["is_morning"],
                    systolic=snapshot["bp"]["systolic"],
                    diastolic=snapshot["bp"]["diastolic"],
                )
            )
            existing_keys["blood_pressure_entries"].add(bp_key)
            inserted["blood_pressure_entries"] += 1

        spo2_key = snapshot["spo2"]["ts"]
        if spo2_key not in existing_keys["spo2_entries"]:
            db.add(
                Spo2Entry(
                    athlete_id=athlete_id,
                    ts=snapshot["spo2"]["ts"],
                    percentage=snapshot["spo2"]["percentage"],
                    source="synthetic",
                )
            )
            existing_keys["spo2_entries"].add(spo2_key)
            inserted["spo2_entries"] += 1

        if current_date.weekday() == 0:
            analysis_key = (current_date, "coach_readiness")
            if analysis_key not in existing_keys["analysis_entries"]:
                db.add(
                    AnalysisEntry(
                        athlete_id=athlete_id,
                        date=current_date,
                        title="coach_readiness",
                        value=snapshot["analysis_value"],
                        notes=f"synthetic pattern={profile.pattern}",
                    )
                )
                existing_keys["analysis_entries"].add(analysis_key)
                inserted["analysis_entries"] += 1

    return inserted


def generate_daily_snapshot(
    *,
    rng: random.Random,
    profile: AthleteSeedProfile,
    current_date: date,
    progress: float,
) -> dict[str, object]:
    weekday = current_date.weekday()
    overload_block = profile.pattern == "overloaded" and (0.30 <= progress <= 0.48 or 0.70 <= progress <= 0.86)
    poor_sleep_block = profile.pattern == "poor_sleep"
    inconsistent_block = profile.pattern == "inconsistent"
    returning_block = profile.pattern == "returning" and progress < 0.22
    improving_bonus = 0.10 if profile.pattern == "improving" else 0.0

    training_probability = {
        "improving": 0.72,
        "stable": 0.64,
        "overloaded": 0.82,
        "poor_sleep": 0.56,
        "inconsistent": 0.42,
        "returning": 0.50,
    }[profile.pattern]
    if weekday in {5, 6}:
        training_probability -= 0.12
    if overload_block:
        training_probability += 0.08
    if returning_block:
        training_probability -= 0.15
    if progress > 0.55 and profile.pattern == "returning":
        training_probability += 0.15

    training_probability = min(0.92, max(0.12, training_probability + rng.uniform(-0.06, 0.06)))
    has_training = rng.random() < training_probability

    sport_profile = sport_defaults(profile.sport)
    fatigue_penalty = (0.12 if overload_block else 0.0) + (0.10 if poor_sleep_block else 0.0)

    if has_training:
        base_duration = sport_profile["duration"] * (0.78 + progress * 0.35 + improving_bonus)
        if overload_block:
            base_duration *= 1.18
        if inconsistent_block:
            base_duration *= rng.uniform(0.65, 1.25)
        if returning_block:
            base_duration *= 0.72

        duration_minutes = int(round(clamp(base_duration + rng.uniform(-10, 10), 25.0, 120.0)))
        avg_hr = int(round(clamp(sport_profile["avg_hr"] + rng.uniform(-8, 8) + fatigue_penalty * 25, 112.0, 178.0)))
        max_hr = int(round(clamp(avg_hr + rng.uniform(18, 32), avg_hr + 8, 196.0)))
        calories = int(round(duration_minutes * sport_profile["calorie_factor"] * rng.uniform(0.92, 1.10)))
        distance_km = round(max(0.0, duration_minutes / 60.0 * sport_profile["speed_kmh"] * rng.uniform(0.88, 1.08)), 2)
        elevation_m = int(round(max(0.0, sport_profile["elevation_factor"] * duration_minutes * rng.uniform(0.6, 1.4))))
        feeling_score = int(round(clamp(8.4 - fatigue_penalty * 18 - abs(duration_minutes - 65) / 32 + rng.uniform(-1.1, 0.9), 3.0, 10.0)))
        training_type = sport_profile["training_type"]
        title = f"{profile.sport} {training_type.title()}"
        start_hour = 6 if weekday in {1, 3, 5} else 18
        start_time = time(hour=start_hour, minute=int(rng.choice((0, 10, 15, 20, 30, 40, 45, 50))))
        hr_zone = "tempo" if avg_hr >= 150 else "aerobic"
        zone2 = max(0, int(duration_minutes * (0.35 if hr_zone == "tempo" else 0.55)))
        zone3 = max(0, int(duration_minutes * (0.28 if hr_zone == "tempo" else 0.18)))
        zone4 = max(0, int(duration_minutes * (0.18 if hr_zone == "tempo" else 0.08)))
        hr_zone_minutes = {
            "zone_2": zone2,
            "zone_3": zone3,
            "zone_4": zone4,
        }
        exercises = [{"name": training_type, "duration_minutes": duration_minutes}]
        training_payload = {
            "title": title,
            "training_type": training_type,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "distance_km": distance_km,
            "elevation_m": elevation_m,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "calories": calories,
            "hr_zone": hr_zone,
            "hr_zone_minutes": hr_zone_minutes,
            "exercises": exercises,
            "feeling_score": feeling_score,
        }
    else:
        training_payload = None
        duration_minutes = 0
        avg_hr = 118 + rng.uniform(-5, 4)
        max_hr = avg_hr + rng.uniform(8, 16)
        feeling_score = int(round(clamp(7.8 - fatigue_penalty * 12 + rng.uniform(-0.8, 0.8), 4.0, 10.0)))

    base_sleep = {
        "improving": 7.9,
        "stable": 7.6,
        "overloaded": 7.1,
        "poor_sleep": 6.1,
        "inconsistent": 7.0,
        "returning": 7.7,
    }[profile.pattern]
    if overload_block:
        base_sleep -= 0.45
    if weekday == 5:
        base_sleep += 0.35
    if inconsistent_block:
        base_sleep += rng.uniform(-1.2, 0.8)
    sleep_hours = clamp(base_sleep + rng.uniform(-0.35, 0.45), 4.8, 9.2)

    deep_minutes = int(round(clamp(sleep_hours * 60 * rng.uniform(0.18, 0.26), 45.0, 155.0)))
    rem_minutes = int(round(clamp(sleep_hours * 60 * rng.uniform(0.16, 0.24), 40.0, 135.0)))
    total_sleep_minutes = int(round(sleep_hours * 60))
    light_minutes = max(20, total_sleep_minutes - deep_minutes - rem_minutes)

    sleep_end_hour = int(clamp(6.0 + (8.2 - sleep_hours) * 0.2 + rng.uniform(-0.3, 0.5), 5.0, 8.0))
    sleep_end_minute = int(rng.choice((0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)))
    sleep_end = datetime.combine(current_date, time(hour=sleep_end_hour, minute=sleep_end_minute), tzinfo=timezone.utc)
    sleep_start = sleep_end - timedelta(minutes=total_sleep_minutes)

    systolic = int(round(clamp(116 + fatigue_penalty * 28 + (7.4 - sleep_hours) * 3.6 + rng.uniform(-4, 5), 102.0, 152.0)))
    diastolic = int(round(clamp(74 + fatigue_penalty * 16 + (7.1 - sleep_hours) * 2.2 + rng.uniform(-3, 4), 62.0, 98.0)))
    bp_ts = datetime.combine(current_date, time(hour=7, minute=int(rng.choice((0, 5, 10, 15, 20)))), tzinfo=timezone.utc)

    spo2 = int(round(clamp(98.0 - fatigue_penalty * 9.0 - max(0.0, 6.7 - sleep_hours) * 1.2 + rng.uniform(-1.0, 0.5), 91.0, 99.0)))
    spo2_ts = bp_ts + timedelta(minutes=3)

    readiness_score = clamp(
        sleep_hours * 10.0
        + feeling_score * 6.0
        + (100.0 - max(0.0, systolic - 118.0) * 1.1)
        + (spo2 - 92.0) * 4.0
        - (duration_minutes * 0.20 if overload_block else duration_minutes * 0.08)
    )
    analysis_value = resolve_analysis_label(readiness_score)

    return {
        "training": training_payload,
        "sleep": {
            "start_ts": sleep_start,
            "end_ts": sleep_end,
            "deep_minutes": deep_minutes,
            "light_minutes": light_minutes,
            "rem_minutes": rem_minutes,
        },
        "bp": {
            "ts": bp_ts,
            "is_morning": True,
            "systolic": systolic,
            "diastolic": diastolic,
        },
        "spo2": {
            "ts": spo2_ts,
            "percentage": spo2,
        },
        "analysis_value": analysis_value,
    }


def sport_defaults(sport: str) -> dict[str, float | str]:
    if sport == "Running":
        return {
            "duration": 58.0,
            "avg_hr": 146.0,
            "calorie_factor": 10.5,
            "speed_kmh": 10.5,
            "elevation_factor": 1.4,
            "training_type": "endurance",
        }
    if sport == "Cycling":
        return {
            "duration": 72.0,
            "avg_hr": 141.0,
            "calorie_factor": 9.4,
            "speed_kmh": 24.0,
            "elevation_factor": 2.1,
            "training_type": "ride",
        }
    if sport == "Swimming":
        return {
            "duration": 54.0,
            "avg_hr": 138.0,
            "calorie_factor": 8.7,
            "speed_kmh": 3.1,
            "elevation_factor": 0.0,
            "training_type": "swim",
        }
    if sport == "Strength":
        return {
            "duration": 68.0,
            "avg_hr": 132.0,
            "calorie_factor": 7.9,
            "speed_kmh": 0.0,
            "elevation_factor": 0.0,
            "training_type": "strength",
        }
    return {
        "duration": 64.0,
        "avg_hr": 144.0,
        "calorie_factor": 9.8,
        "speed_kmh": 13.0,
        "elevation_factor": 1.8,
        "training_type": "mixed",
    }


def resolve_analysis_label(readiness_score: float) -> str:
    if readiness_score >= 82.0:
        return "excellent"
    if readiness_score >= 70.0:
        return "good"
    if readiness_score >= 55.0:
        return "warning"
    return "poor"


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


if __name__ == "__main__":
    main()
