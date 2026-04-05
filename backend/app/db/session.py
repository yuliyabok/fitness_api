# Файл: создание движка и сессий SQLAlchemy для работы с базой данных.

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Engine is shared across requests.
#engine управляет подключением к БД
#pool_pre_ping=True — перед повторным использованием соединения проверяется, живо ли оно
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)

# Session factory for request-scoped DB sessions.
#создает новую сессию для каждого запроса
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)

#предоставляет сессию для бд и гарантирует ее закрытие после исползования
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
