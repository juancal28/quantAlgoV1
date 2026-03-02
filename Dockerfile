# ---- Build stage ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build python3-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: Build tools — cached until build-system requires change
RUN pip install --no-cache-dir scikit-build-core pybind11 cmake ninja

# Layer 2: CPU-only PyTorch + transformers (~200MB vs ~2GB with CUDA)
# Railway has no GPU, so CUDA is dead weight. This layer almost never changes.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir transformers

# Layer 3: Pre-download FinBERT model — cached until transformers version changes
RUN python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
    AutoTokenizer.from_pretrained('ProsusAI/finbert'); \
    AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert')"

# Layer 4: App dependencies — cached until pyproject.toml changes
COPY pyproject.toml ./
RUN python -c "\
import tomllib, pathlib; \
t = tomllib.load(open('pyproject.toml', 'rb')); \
deps = t['project']['dependencies']; \
pathlib.Path('/tmp/requirements.txt').write_text('\n'.join(deps))" \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# Layer 5: Build C++ extension — only rebuilds when cpp/ or source changes
COPY cpp/ ./cpp/
COPY core/ ./core/
COPY apps/ ./apps/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN pip install --no-cache-dir --no-build-isolation --no-deps .

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

# Default port for local dev; Railway overrides via $PORT env var
ENV PORT=8080

# Entrypoint handles alembic migrations when RUN_MIGRATIONS=true
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

# Shell form so $PORT is expanded at runtime
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT"]
