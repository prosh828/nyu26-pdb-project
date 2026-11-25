#!/usr/bin/env bash
# Back up the Recco database to db/backup/recco_<date>.sql
# Usage (from the repo root, containers running): bash db/backup.sh
set -euo pipefail

OUT_DIR="db/backup"
OUT_FILE="$OUT_DIR/recco_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$OUT_DIR"

docker compose -f env/docker-compose.yml exec -T db sh -c \
  'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' \
  > "$OUT_FILE"

echo "Backup written to $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"#!/usr/bin/env bash
# Back up the Recco database to db/backup/recco_<date>.sql
# Usage (from the repo root, containers running): bash db/backup.sh
set -euo pipefail

OUT_DIR="db/backup"
OUT_FILE="$OUT_DIR/recco_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$OUT_DIR"

docker compose -f env/docker-compose.yml exec -T db sh -c \
  'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' \
  > "$OUT_FILE"

echo "Backup written to $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"#!/usr/bin/env bash
# Back up the Recco database to db/backup/recco_<date>.sql
# Usage (from the repo root, containers running): bash db/backup.sh
set -euo pipefail

OUT_DIR="db/backup"
OUT_FILE="$OUT_DIR/recco_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$OUT_DIR"

docker compose -f env/docker-compose.yml exec -T db sh -c \
  'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' \
  > "$OUT_FILE"

echo "Backup written to $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"#!/usr/bin/env bash
# Back up the Recco database to db/backup/recco_<date>.sql
# Usage (from the repo root, containers running): bash db/backup.sh
set -euo pipefail

OUT_DIR="db/backup"
OUT_FILE="$OUT_DIR/recco_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$OUT_DIR"

docker compose -f env/docker-compose.yml exec -T db sh -c \
  'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' \
  > "$OUT_FILE"

echo "Backup written to $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"

