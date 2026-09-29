FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      tesseract-ocr=5.3.0-2 \
      tesseract-ocr-eng=1:4.1.0-2 \
      tesseract-ocr-rus=1:4.1.0-2 \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version 2>&1 | grep '^tesseract 5\.' \
    && tesseract --list-langs 2>&1 | grep -x 'eng' \
    && tesseract --list-langs 2>&1 | grep -x 'rus'

# Public Ministry root CA, pinned to the reviewed PEM bytes. Keep TLS validation on.
COPY infra/certs/russian-trusted-root-ca.crt /usr/local/share/ca-certificates/russian-trusted-root-ca.crt
RUN echo '0819977502d9aed2234830f6ffb91f82f401d3674c6e51dd19e16d8b3dbf0eb4  /usr/local/share/ca-certificates/russian-trusted-root-ca.crt' \
      | sha256sum -c - \
    && update-ca-certificates

COPY apps/backend/requirements.lock /tmp/backend-requirements.lock
RUN pip install --no-cache-dir -r /tmp/backend-requirements.lock

COPY apps/backend/app /workspace/app
COPY packages/housing_engine/src/housing_engine /workspace/housing_engine
COPY apps/backend/migrations /workspace/migrations
COPY apps/backend/alembic.ini /workspace/alembic.ini
COPY fixtures/receipts/water-2026-08.json fixtures/receipts/water-2026-09.json /workspace/fixtures/receipts/
COPY fixtures/receipts/city-moscow-water-2026-08.json fixtures/receipts/city-moscow-water-2026-09.json \
     fixtures/receipts/city-lyubertsy-water-2026-08.json fixtures/receipts/city-lyubertsy-water-2026-09.json \
     fixtures/receipts/city-preview-cohort-v1.json /workspace/fixtures/receipts/
COPY fixtures/receipts/manifest.json /workspace/fixtures/receipts/manifest.json
COPY knowledge /workspace/knowledge

RUN groupadd --system app && useradd --system --gid app --home /workspace app \
    && mkdir /storage && chown app:app /storage \
    && chgrp -R app /workspace && chmod -R g-w,g+rX /workspace
USER app

# Fail the build if checkout file modes would hide migrations or runtime data
# from the non-root process used by migrate, api and worker.
RUN python -c "from pathlib import Path; from alembic.config import Config; import housing_engine; root = Path('/workspace'); location = Config(str(root / 'alembic.ini')).get_main_option('script_location'); assert location and Path(location).is_dir(); assert (root / 'knowledge/topics/bill_change.yaml').read_text(encoding='utf-8'); assert (root / 'fixtures/receipts/manifest.json').read_text(encoding='utf-8'); assert (root / 'fixtures/receipts/city-preview-cohort-v1.json').read_text(encoding='utf-8')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
