#!/usr/bin/env bash
# create jsonl from a single document with paragraphs
# usage: cat article.txt | ./map-paragraphs.sh
set -euo pipefail

jq -Rsc '
  gsub("\\r\\n"; "\n")
  | gsub("\n[ \\t]*\n+"; "\u0000")
  | split("\u0000")
  | map(gsub("^[[:space:]]+|[[:space:]]+$"; "") | select(length > 0))
  | to_entries[]
  | {id: (.key + 1), text: .value}
'
