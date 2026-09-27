FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr=5.3.0-2 \
      tesseract-ocr-eng=1:4.1.0-2 \
      tesseract-ocr-rus=1:4.1.0-2 \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version 2>&1 | grep '^tesseract 5\.' \
    && tesseract --list-langs 2>&1 | grep -x 'eng' \
    && tesseract --list-langs 2>&1 | grep -x 'rus'

COPY apps/backend/requirements.lock /tmp/backend-requirements.lock
RUN pip install --no-cache-dir -r /tmp/backend-requirements.lock

COPY apps/backend/app /workspace/app
COPY packages/housing_engine/src/housing_engine /workspace/housing_engine
COPY apps/backend/migrations /workspace/migrations
COPY apps/backend/alembic.ini /workspace/alembic.ini
COPY fixtures/receipts/water-2026-08.json fixtures/receipts/water-2026-09.json /workspace/fixtures/receipts/
COPY fixtures/receipts/manifest.json /workspace/fixtures/receipts/manifest.json
COPY knowledge /workspace/knowledge

RUN groupadd --system app && useradd --system --gid app --home /workspace app \
    && mkdir /storage && chown app:app /storage
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
