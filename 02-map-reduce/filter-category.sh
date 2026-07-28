#!/usr/bin/env bash
# 
# usage: ./filter-classify.sh < records.jsonl | ./filter-category.sh bug
set -euo pipefail

if (( $# != 1 )); then
  echo "Usage: $0 CATEGORY" >&2
  exit 2
fi

jq -c --arg category "$1" '
  if type != "object" or (.category | type != "string") then
    error("expected objects with a string field named category")
  elif .category == $category then
    .
  else
    empty
  end
'
