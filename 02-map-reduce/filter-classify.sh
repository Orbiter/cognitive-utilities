#!/usr/bin/env bash
# Usage: ./map-lines.sh < issues.txt | ./filter-classify.sh
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
line_number=0

while IFS= read -r line || [[ -n "$line" ]]; do
  ((line_number += 1))
  record=$(jq -ce '
    if type == "object" and (.text | type == "string") then .
    else error("expected an object with a string field named text")
    end
  ' <<<"$line") || {
    echo "filter-classify.sh: invalid record on line $line_number" >&2
    exit 1
  }

  text=$(jq -r '.text' <<<"$record")
  category=$(printf '%s\n' "$text" | "$script_dir/../01-cognitive-filters/classify.sh")

  jq -cn --argjson record "$record" --arg category "$category" \
    '$record + {category: $category}'
done
