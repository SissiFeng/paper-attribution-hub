FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    postgresql-client \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/app/ ./app/
COPY tools/author-paper-monitor/paper_monitor/ ./paper_monitor/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini .

# Reference/config data only. Corpus papers come from Zotero at runtime.
COPY data/ac_members.csv /data/ac_members.csv
COPY data/institution_aliases.csv /data/institution_aliases.csv
COPY data/topic_taxonomy.yaml /data/topic_taxonomy.yaml
COPY data/domain_vocabulary.yaml /data/domain_vocabulary.yaml
COPY data/retrieval_operationalization_terms.yaml /data/retrieval_operationalization_terms.yaml
COPY data/eval_labels_silver.csv /data/eval_labels_silver.csv
COPY data/training_labels.csv /data/training_labels.csv
COPY data/validation_labels.csv /data/validation_labels.csv
COPY data/eval_labels.csv /data/eval_labels.csv
COPY data/sdl_entities.yaml /data/sdl_entities.yaml
COPY data/sdl_labs.yaml /data/sdl_labs.yaml
COPY data/sdl_targets.yaml /data/sdl_targets.yaml
COPY data/method_stages.yaml /data/method_stages.yaml
COPY data/example_tkus.yaml /data/example_tkus.yaml

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

# Entrypoint: bootstrap + optional Zotero sync never block boot;
# uvicorn always starts so /health and /debug/* stay reachable for diagnosis.
CMD ["python", "-m", "app.scripts.serve"]
