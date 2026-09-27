FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace

COPY apps/backend/requirements.lock /tmp/backend-requirements.lock
RUN pip install --no-cache-dir -r /tmp/backend-requirements.lock

COPY apps/backend/app /workspace/app
COPY apps/backend/migrations /workspace/migrations
COPY apps/backend/alembic.ini /workspace/alembic.ini
COPY fixtures/receipts/water-2026-08.json fixtures/receipts/water-2026-09.json /workspace/fixtures/receipts/

RUN groupadd --system app && useradd --system --gid app --home /workspace app \
    && mkdir /storage && chown app:app /storage
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
