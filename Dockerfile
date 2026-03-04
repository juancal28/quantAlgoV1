# syntax=docker/dockerfile:1.4
# ---- Build stage ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build python3-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: Build tools — almost never changes
RUN --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip install scikit-build-core pybind11 cmake ninja

# Layer 2: App dependencies — cached until pyproject.toml changes
# NOTE: torch/transformers/FinBERT are NOT installed here. They live on
# a Railway persistent volume and are set up at runtime by entrypoint.sh.
COPY pyproject.toml ./
RUN --mount=type=cache,id=pip,target=/root/.cache/pip \
    python -c "\
import tomllib, pathlib; \
t = tomllib.load(open('pyproject.toml', 'rb')); \
deps = t['project']['dependencies']; \
pathlib.Path('/tmp/requirements.txt').write_text('\n'.join(deps))" \
    && pip install -r /tmp/requirements.txt

# Layer 3: Build C++ extension via cmake — only rebuilds when cpp/ changes
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

# Copy application code
COPY . .

ENV PORT=8080

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT"]
