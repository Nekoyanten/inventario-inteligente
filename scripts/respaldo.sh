#!/bin/sh
# Copia de seguridad diaria de PostgreSQL con rotación.
#   Uso:  DATABASE_URL=postgres://... ./scripts/respaldo.sh [carpeta]   (cron: 30 3 * * *)
#   Restaurar:  gunzip -c respaldo-AAAAMMDD-HHMM.sql.gz | psql "$DATABASE_URL"
set -eu
DESTINO="${1:-./respaldos}"
DIAS="${DIAS_RETENCION:-30}"
mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/respaldo-$(date +%Y%m%d-%H%M).sql.gz"
pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip -9 > "$ARCHIVO"
# Verificación mínima: el archivo no está vacío y es gzip válido
gzip -t "$ARCHIVO" && [ -s "$ARCHIVO" ]
find "$DESTINO" -name 'respaldo-*.sql.gz' -mtime +"$DIAS" -delete
echo "Respaldo listo: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"
