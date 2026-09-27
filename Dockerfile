FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# collectstatic necesita una SECRET_KEY aunque no se use
RUN SECRET_KEY=build DEBUG=False python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /app/media && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "scripts/iniciar.sh"]
