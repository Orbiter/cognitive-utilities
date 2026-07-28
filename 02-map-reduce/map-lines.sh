#!/usr/bin/env bash
# create jsonl from lines of a single document 
# usage: printf 'Server unavailable.\nAdd dark mode.\nHow do I log in?\n' | ./map-lines.sh
set -euo pipefail

id=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "${line//[[:space:]]/}" ]] && continue
  ((id += 1))
  jq -cn --argjson id "$id" --arg text "$line" \
    '{id: $id, text: $text}'
done
