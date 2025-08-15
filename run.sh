#!/bin/bash
set -e

python manage.py collectstatic --no-input

PORT=${PORT:-8055}

exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --access-logfile "-" \
    --timeout 3600 \
    --workers 2 \
    mchangohub.wsgi:application
