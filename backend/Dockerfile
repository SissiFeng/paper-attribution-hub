FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/app/ ./app/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini .

# Config data (excludes sample_papers.csv, eval_labels.csv, fulltexts/)
COPY data/ac_members.csv /data/ac_members.csv
COPY data/ac_core_papers.csv /data/ac_core_papers.csv
COPY data/institution_aliases.csv /data/institution_aliases.csv
COPY data/topic_taxonomy.yaml /data/topic_taxonomy.yaml
COPY data/domain_vocabulary.yaml /data/domain_vocabulary.yaml
COPY data/retrieval_operationalization_terms.yaml /data/retrieval_operationalization_terms.yaml
COPY data/eval_labels_silver.csv /data/eval_labels_silver.csv
COPY data/sdl_entities.yaml /data/sdl_entities.yaml
COPY data/sdl_labs.yaml /data/sdl_labs.yaml
COPY data/sdl_targets.yaml /data/sdl_targets.yaml
COPY data/method_stages.yaml /data/method_stages.yaml
COPY data/example_tkus.yaml /data/example_tkus.yaml
COPY data/tier1_tier2_merged_classification_ready.csv.gz /data/tier1_tier2_merged_classification_ready.csv.gz
COPY data/ac_publications_focused_grid_view.csv.gz /data/ac_publications_focused_grid_view.csv.gz

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

# Demo-safe entrypoint: bootstrap + seed are best-effort and never block boot;
# uvicorn always starts so /health and /debug/* stay reachable for diagnosis.
CMD ["python", "-m", "app.scripts.serve"]
