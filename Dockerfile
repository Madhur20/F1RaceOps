# F1RaceOps backend — production image
FROM python:3.12-slim

WORKDIR /app

# System deps needed to build psycopg2 from source if a wheel isn't
# available for the target platform; kept minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# Railway (and most PaaS providers) inject PORT at runtime; default to
# 8000 for any environment that doesn't set it explicitly.
ENV PORT=8000
EXPOSE 8000

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}