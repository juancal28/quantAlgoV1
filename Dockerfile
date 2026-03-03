# syntax=docker/dockerfile:1.4
# ---- Build stage ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build python3-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build arg: set to "mock" to skip torch/FinBERT (~1GB savings, ~3min faster)
#   railway variables --set SENTIMENT_PROVIDER=mock  (or finbert)
#   Then in railway.toml: [build] -> dockerfileBuildArgs
ARG SENTIMENT_PROVIDER=finbert

# Layer 1: Build tools — almost never changes
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install scikit-build-core pybind11 cmake ninja

# Layer 2: CPU-only PyTorch + transformers — ONLY when FinBERT is needed
# Skipping this saves ~500MB download + install time
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$SENTIMENT_PROVIDER" = "finbert" ]; then \
        pip install torch --index-url https://download.pytorch.org/whl/cpu && \
        pip install transformers; \
    fi

# Layer 3: Pre-download FinBERT model — ONLY when needed (~500MB)
RUN if [ "$SENTIMENT_PROVIDER" = "finbert" ]; then \
        python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
            AutoTokenizer.from_pretrained('ProsusAI/finbert'); \
            AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert')"; \
    fi

# Layer 4: App dependencies — cached until pyproject.toml changes
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "\
import tomllib, pathlib; \
t = tomllib.load(open('pyproject.toml', 'rb')); \
deps = t['project']['dependencies']; \
pathlib.Path('/tmp/requirements.txt').write_text('\n'.join(deps))" \
    && pip install -r /tmp/requirements.txt

# Layer 5: Build C++ extension via cmake directly — only rebuilds when cpp/ changes
# Decoupled from Python source so Python-only changes skip this layer entirely
COPY cpp/ ./cpp/
RUN cmake -S cpp -B cpp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -Dpybind11_DIR=$(python -c "import pybind11; print(pybind11.get_cmake_dir())") \
    && cmake --build cpp/build --parallel \
    && cp cpp/build/_quant_core*.so /usr/local/lib/python3.11/site-packages/

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages + C++ extension from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy HuggingFace model cache (empty dir if SENTIMENT_PROVIDER=mock)
COPY --from=builder /root/.cache/huggingface/ /root/.cache/huggingface/

# Copy application code — this is the cheapest layer, changes most often
COPY . .

ENV PORT=8080

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT"]
