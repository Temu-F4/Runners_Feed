#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly UNIT_SOURCE="${PROJECT_ROOT}/deploy/systemd"
readonly UNIT_TARGET="${RUNNERS_FEED_SYSTEMD_UNIT_TARGET:-/etc/systemd/system}"
readonly SYSTEMCTL_BIN="${RUNNERS_FEED_SYSTEMCTL_BIN:-systemctl}"
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
readonly TIMERS=(
  runners-feed-cert-renew.timer
  runners-feed-db-backup.timer
  runners-feed-db-backup-verify.timer
  runners-feed-model-quality-watchdog.timer
)

changed=0

for unit in "${UNITS[@]}"; do
  if [[ ! -r "${UNIT_SOURCE}/${unit}" ]]; then
    echo "Missing systemd unit: ${UNIT_SOURCE}/${unit}" >&2
    exit 1
  fi
  if [[ -r "${UNIT_TARGET}/${unit}" ]] \
    && cmp --silent "${UNIT_SOURCE}/${unit}" "${UNIT_TARGET}/${unit}"; then
    continue
  fi
  sudo -n install -o root -g root -m 0644 \
    "${UNIT_SOURCE}/${unit}" "${UNIT_TARGET}/${unit}"
  changed=1
done

if (( changed )); then
  sudo -n "${SYSTEMCTL_BIN}" daemon-reload
fi

for timer in "${TIMERS[@]}"; do
  if ! "${SYSTEMCTL_BIN}" is-enabled --quiet "${timer}" \
    || ! "${SYSTEMCTL_BIN}" is-active --quiet "${timer}"; then
    sudo -n "${SYSTEMCTL_BIN}" enable --now "${TIMERS[@]}"
    break
  fi
done

echo "Runners Feed systemd units synchronized"
