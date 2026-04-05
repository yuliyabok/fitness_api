# Файл: настройка окружения Alembic и подключения миграций к базе данных.

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
from app.models.analysis import AnalysisEntry  # noqa: F401
from app.models.blood_pressure import BloodPressureEntry  # noqa: F401
from app.models.calorie import CalorieEntry  # noqa: F401
from app.models.cycle import CycleEvent, CycleSettings  # noqa: F401
from app.models.sleep import SleepEntry  # noqa: F401
from app.models.spo2 import Spo2Entry  # noqa: F401
from app.models.training import Training  # noqa: F401
from app.models.user import AppUser, AthleteProfile, CoachProfile  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)
# Сервер читает переменную DATABASE_URL из .env и передает ее в Alembic для подключения к БД.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

