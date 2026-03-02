# ---- Build stage ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake python3-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY cpp/ ./cpp/
COPY core/ ./core/
COPY apps/ ./apps/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Build C++ extension + install all deps including FinBERT (sentiment extra)
RUN pip install --no-cache-dir ".[sentiment]"

# Pre-download FinBERT model so it's baked into the image
RUN python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
    AutoTokenizer.from_pretrained('ProsusAI/finbert'); \
    AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert')"

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages + cached HuggingFace model
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /root/.cache/huggingface/ /root/.cache/huggingface/

# Copy application code
COPY . .

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
