#!/bin/sh
# Arranque en producción: migraciones + (opcional) superusuario y demo + servidor WSGI.
set -e
python manage.py migrate --noinput

# Superusuario inicial: define DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL y DJANGO_SUPERUSER_PASSWORD.
# Si ya existe, no hace nada.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --noinput >/dev/null 2>&1 && echo "Superusuario creado" || echo "Superusuario ya existe"
fi

# Negocios de demostración (docs/DEMO_NEGOCIOS.md): CARGAR_DEMO=1. Se cargan en segundo plano para que la app
# arranque de una vez; si ya existen, el comando lo avisa y no hace nada.
if [ "$CARGAR_DEMO" = "1" ]; then
  (python -u manage.py cargar_demo_negocios --dias "${DEMO_DIAS:-30}" || true) &
fi

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" \
  --timeout 120 --access-logfile - --forwarded-allow-ips="*"
