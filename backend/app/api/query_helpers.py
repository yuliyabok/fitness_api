# Файл: вспомогательные функции для пагинации и фильтрации по датам в API-маршрутах.

from __future__ import annotations

from datetime import date, datetime, time, timedelta


def apply_date_range(statement, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        statement = statement.where(column >= date_from)
    if date_to is not None:
        statement = statement.where(column <= date_to)
    return statement


def apply_datetime_date_range(statement, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        statement = statement.where(column >= datetime.combine(date_from, time.min))
    if date_to is not None:
        statement = statement.where(column < datetime.combine(date_to + timedelta(days=1), time.min))
    return statement


def apply_pagination(statement, limit: int | None, offset: int):
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    return statement
