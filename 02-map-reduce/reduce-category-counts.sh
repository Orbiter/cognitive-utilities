#!/usr/bin/env bash
# 
# usage: ./filter-classify.sh < records.jsonl | ./reduce-category-counts.sh
set -euo pipefail

jq -sc '
  if all(.[]; type == "object" and (.category | type == "string")) then
    {
      total: length,
      categories: (
        group_by(.category)
        | map({key: .[0].category, value: length})
        | from_entries
      )
    }
  else
    error("expected objects with a string field named category")
  end
'
