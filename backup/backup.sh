#!/bin/sh
set -eu

backup_dir=/backups
mkdir -p "$backup_dir"

while true; do
  timestamp=$(date -u +%Y%m%d_%H%M%S)
  output="$backup_dir/catastro_minero_${timestamp}.sql.gz"
  echo "Creando backup: $output"
  until pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
    sleep 5
  done
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner --no-privileges | gzip > "$output"
  find "$backup_dir" -type f -name '*.sql.gz' -mtime +7 -delete
  echo "Backup completado. Próximo backup en 24 horas."
  sleep 86400
done
