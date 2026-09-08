#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly UNIT_SOURCE="${PROJECT_ROOT}/deploy/systemd"
readonly UNIT_TARGET="/etc/systemd/system"
readonly UNITS=(
  runners-feed-cert-renew.service
  runners-feed-cert-renew.timer
  runners-feed-db-backup.service
  runners-feed-db-backup.timer
  runners-feed-db-backup-verify.service
  runners-feed-db-backup-verify.timer
  runners-feed-model-quality-watchdog.service
  runners-feed-model-quality-watchdog.timer
)

for unit in "${UNITS[@]}"; do
  if [[ ! -r "${UNIT_SOURCE}/${unit}" ]]; then
    echo "Missing systemd unit: ${UNIT_SOURCE}/${unit}" >&2
    exit 1
  fi
  sudo -n install -o root -g root -m 0644 \
    "${UNIT_SOURCE}/${unit}" "${UNIT_TARGET}/${unit}"
done

sudo -n systemctl daemon-reload
sudo -n systemctl enable --now \
  runners-feed-cert-renew.timer \
  runners-feed-db-backup.timer \
  runners-feed-db-backup-verify.timer \
  runners-feed-model-quality-watchdog.timer

echo "Runners Feed systemd units synchronized"
