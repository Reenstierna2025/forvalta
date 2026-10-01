#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
kind="${1:-diff}"
case "$kind" in full|diff|incr) ;; *) echo 'Expected full, diff or incr'; exit 1;; esac
docker compose exec -T --user postgres db pgbackrest --stanza=forvalta --type="$kind" backup
docker compose exec -T --user postgres db pgbackrest --stanza=forvalta check
