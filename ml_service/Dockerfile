FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ml_service/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY ml_service /app/ml_service

EXPOSE 9000

CMD ["uvicorn", "ml_service.main:app", "--host", "0.0.0.0", "--port", "9000"]
