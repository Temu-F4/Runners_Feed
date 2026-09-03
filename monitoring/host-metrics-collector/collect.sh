#!/bin/sh

set -eu

OUTPUT_DIR=/textfile-collector
PROCESS_INTERVAL_SECONDS="${PROCESS_INTERVAL_SECONDS:-15}"
STORAGE_INTERVAL_SECONDS="${STORAGE_INTERVAL_SECONDS:-300}"
TOP_PROCESS_COUNT="${TOP_PROCESS_COUNT:-20}"
TOP_STORAGE_COUNT="${TOP_STORAGE_COUNT:-20}"
LARGE_FILE_MIN_BYTES="${LARGE_FILE_MIN_BYTES:-10485760}"

escape_label() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

collect_process_metrics() {
  candidates="$OUTPUT_DIR/processes.candidates"
  output_tmp="$OUTPUT_DIR/processes.prom.tmp"
  output="$OUTPUT_DIR/processes.prom"
  : > "$candidates"

  for status_file in /host/proc/[0-9]*/status; do
    [ -r "$status_file" ] || continue
    pid="${status_file#/host/proc/}"
    pid="${pid%/status}"
    rss_kib="$(awk '$1 == "VmRSS:" { print $2; exit }' "$status_file" 2>/dev/null || true)"
    [ -n "$rss_kib" ] || continue
    process_name="$(awk '$1 == "Name:" { print $2; exit }' "$status_file" 2>/dev/null || true)"
    executable="$(readlink "/host/proc/$pid/exe" 2>/dev/null || true)"
    if [ -z "$executable" ] && [ -r "/host/proc/$pid/cmdline" ]; then
      executable="$(tr '\000' ' ' < "/host/proc/$pid/cmdline" 2>/dev/null | awk '{ print $1; exit }' || true)"
    fi
    [ -n "$process_name" ] || process_name=unknown
    [ -n "$executable" ] || executable=unknown
    printf '%s\t%s\t%s\t%s\n' "$rss_kib" "$pid" "$process_name" "$executable" >> "$candidates"
  done

  {
    printf '# HELP runners_feed_host_process_resident_memory_bytes Resident memory used by a host process. Only the largest processes are exported.\n'
    printf '# TYPE runners_feed_host_process_resident_memory_bytes gauge\n'
    sort -nr "$candidates" | head -n "$TOP_PROCESS_COUNT" | while IFS="$(printf '\t')" read -r rss_kib pid process_name executable; do
      printf 'runners_feed_host_process_resident_memory_bytes{pid="%s",process="%s",executable="%s"} %s\n' \
        "$(escape_label "$pid")" \
        "$(escape_label "$process_name")" \
        "$(escape_label "$executable")" \
        "$((rss_kib * 1024))"
    done
  } > "$output_tmp"

  mv "$output_tmp" "$output"
  rm -f "$candidates"
}

append_directory_candidates() {
  base_path="$1"
  max_depth="$2"
  [ -d "$base_path" ] || return 0
  du -x -k -d "$max_depth" "$base_path" 2>/dev/null || true
}

collect_storage_metrics() {
  directories="$OUTPUT_DIR/directories.candidates"
  files="$OUTPUT_DIR/files.candidates"
  directory_output_tmp="$OUTPUT_DIR/directories.prom.tmp"
  file_output_tmp="$OUTPUT_DIR/files.prom.tmp"
  : > "$directories"
  : > "$files"

  {
    append_directory_candidates /host/home/ubuntu 2
    append_directory_candidates /host/var/lib/docker 2
    append_directory_candidates /host/var/log 2
    append_directory_candidates /host/tmp 1
  } | sort -nr | head -n "$TOP_STORAGE_COUNT" > "$directories"

  for search_root in /host/home/ubuntu /host/var/log /host/var/lib/docker/volumes; do
    [ -d "$search_root" ] || continue
    find "$search_root" -xdev -type f -size "+${LARGE_FILE_MIN_BYTES}c" -exec du -k '{}' ';' 2>/dev/null || true
  done | sort -nr | head -n "$TOP_STORAGE_COUNT" > "$files"

  {
    printf '# HELP runners_feed_host_directory_size_bytes Disk space used by a selected host directory.\n'
    printf '# TYPE runners_feed_host_directory_size_bytes gauge\n'
    while IFS="$(printf '\t')" read -r size_kib host_path; do
      [ -n "$host_path" ] || continue
      display_path="${host_path#/host}"
      printf 'runners_feed_host_directory_size_bytes{path="%s"} %s\n' \
        "$(escape_label "$display_path")" "$((size_kib * 1024))"
    done < "$directories"
  } > "$directory_output_tmp"

  {
    printf '# HELP runners_feed_host_large_file_size_bytes Size of a large host file. Only files at least 10 MiB in selected paths are considered.\n'
    printf '# TYPE runners_feed_host_large_file_size_bytes gauge\n'
    while IFS="$(printf '\t')" read -r size_kib host_path; do
      [ -n "$host_path" ] || continue
      display_path="${host_path#/host}"
      printf 'runners_feed_host_large_file_size_bytes{path="%s"} %s\n' \
        "$(escape_label "$display_path")" "$((size_kib * 1024))"
    done < "$files"
  } > "$file_output_tmp"

  mv "$directory_output_tmp" "$OUTPUT_DIR/directories.prom"
  mv "$file_output_tmp" "$OUTPUT_DIR/files.prom"
  rm -f "$directories" "$files"
}

mkdir -p "$OUTPUT_DIR"
next_storage_collection=0

while true; do
  collect_process_metrics
  current_time="$(date +%s)"
  if [ "$current_time" -ge "$next_storage_collection" ]; then
    collect_storage_metrics
    next_storage_collection=$((current_time + STORAGE_INTERVAL_SECONDS))
  fi
  sleep "$PROCESS_INTERVAL_SECONDS"
done
