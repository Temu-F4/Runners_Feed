#!/usr/bin/env bash

set -euo pipefail

readonly CLEANUP_THRESHOLD="${CI_DISK_CLEANUP_THRESHOLD_PERCENT:-75}"
readonly FAILURE_THRESHOLD="${CI_DISK_FAILURE_THRESHOLD_PERCENT:-90}"
readonly DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}')"

disk_usage_percent() {
  df -P "${DOCKER_ROOT}" | awk 'NR == 2 {gsub(/%/, "", $5); print $5}'
}

if [[ ! "${CLEANUP_THRESHOLD}" =~ ^[0-9]+$ ]] \
  || [[ ! "${FAILURE_THRESHOLD}" =~ ^[0-9]+$ ]] \
  || (( CLEANUP_THRESHOLD >= FAILURE_THRESHOLD )) \
  || (( FAILURE_THRESHOLD > 100 )); then
  echo "Invalid CI disk guard thresholds" >&2
  exit 2
fi

before="$(disk_usage_percent)"
echo "CI Docker filesystem usage: ${before}% (${DOCKER_ROOT})"

if (( before >= CLEANUP_THRESHOLD )); then
  echo "Cleaning unused CI containers, images, and build cache older than 24h"
  docker container prune --force --filter until=24h
  docker image prune --force --filter until=24h
  docker builder prune --force --filter until=24h
fi

after="$(disk_usage_percent)"
if (( after >= FAILURE_THRESHOLD )); then
  echo "CI disk usage is still above the safe build threshold; removing all unused Docker data"
  docker container prune --force
  docker image prune --all --force
  docker builder prune --all --force
  after="$(disk_usage_percent)"
fi

echo "CI Docker filesystem usage after guard: ${after}%"
if (( after >= FAILURE_THRESHOLD )); then
  echo "CI disk usage remains above the safe build threshold" >&2
  exit 1
fi
