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

exec "$@"
