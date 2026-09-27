#!/bin/sh
# Arranque en producción: migraciones + servidor WSGI.
set -e
python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" \
  --timeout 60 --access-logfile - --forwarded-allow-ips="*"
