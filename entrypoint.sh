#!/bin/sh
set -e

# Run Alembic migrations with retry (only when RUN_MIGRATIONS=true)
if [ "$RUN_MIGRATIONS" = "true" ]; then
    for i in 1 2 3 4 5; do
        alembic upgrade head && break
        echo "Alembic retry $i..."
        sleep 5
    done
fi

# Dispatch based on SERVICE_ROLE (api|worker|beat), default to api
ROLE="${SERVICE_ROLE:-api}"

case "$ROLE" in
    api)
        exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-8080}"
        ;;
    worker)
        exec celery -A apps.scheduler.worker worker --loglevel=info --concurrency="${CELERY_WORKER_CONCURRENCY:-2}"
        ;;
    beat)
        exec celery -A apps.scheduler.worker beat --loglevel=info
        ;;
    *)
        echo "FATAL: Unknown SERVICE_ROLE='$ROLE'. Must be api, worker, or beat."
        exit 1
        ;;
esac
