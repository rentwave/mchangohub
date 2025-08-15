#!/bin/bash

python manage.py collectstatic --no-input
PORT=8055
exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --access-logfile - \
    --timeout 3600 \
    mchangohub.wsgi:application -w 2
