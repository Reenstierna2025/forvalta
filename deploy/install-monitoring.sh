#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test "$(pwd)" = /opt/forvalta || { echo 'Install under /opt/forvalta, or adapt and review the systemd paths first.'; exit 1; }
# Do not activate schedules until a real coherent backup and restore have succeeded.
python3 deploy/recovery.py checkpoint
python3 deploy/restore-drill.py
install -m 0644 deploy/systemd/* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now forvalta-checkpoint.timer forvalta-health.timer forvalta-backup-full.timer forvalta-backup-diff.timer forvalta-restore-drill.timer
