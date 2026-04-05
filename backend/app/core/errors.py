# Файл: обработчики ошибок FastAPI для совместимого ответа клиенту.

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def _format_validation_error(exc: RequestValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        raw_loc = error.get("loc", ())
        location = ".".join(str(item) for item in raw_loc if item != "body")
        message = error.get("msg", "Invalid value")
        messages.append(f"{location}: {message}" if location else message)
    if messages:
        return "; ".join(messages)
    return "Validation error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _format_validation_error(exc)},
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(
        _request: Request,
        _exc: IntegrityError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Data conflict"},
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        _request: Request,
        _exc: SQLAlchemyError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Database error"},
        )
