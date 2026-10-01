#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo 'Run python3 deploy/configure.py and configure .env first.'; exit 1; }
docker compose config --quiet
docker compose --profile operations build
docker compose up -d --wait --wait-timeout 300 db scanner
docker compose exec -T --user postgres db pgbackrest --stanza=forvalta stanza-create
docker compose exec -T --user postgres db pgbackrest --stanza=forvalta check
docker compose run --rm api python manage.py migrate --noinput
docker compose run --rm api python manage.py check --deploy --fail-level WARNING
docker compose exec -T --user postgres db pgbackrest --stanza=forvalta --type=full backup
docker compose up -d api worker web
echo 'Services started. Create the first administrator using docker compose exec api python manage.py createsuperuser.'
echo 'Production acceptance still requires the documented storage/restore and security checks.'
