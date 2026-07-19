#!/usr/bin/env bash
# Usage: ./filter-triage.sh < records.jsonl | ./reduce-report.sh
set -euo pipefail

records=$(jq -sc '
  if length == 0 then error("expected at least one JSONL record")
  elif all(.[]; type == "object") then .
  else error("expected a sequence of JSON objects")
  end
')
record_count=$(jq 'length' <<<"$records")
records_json=$(jq -Rn --arg value "$records" '$value')

report=$(curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -ec '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": false,
  "messages": [
    {"role": "system", "content": "Reduce the JSON array into one concise report. Identify shared themes and practical next actions using only the supplied records."},
    {"role": "user", "content": $records_json}
  ],
  "response_format": {"type": "json_schema",
    "json_schema": {"strict": true,
      "schema": {"type": "object",
        "properties": {
          "overall_summary": {"type": "string"},
          "common_themes": {
            "type": "array", "items": {"type": "string"},
            "minItems": 1, "maxItems": 5
          },
          "recommended_actions": {
            "type": "array", "items": {"type": "string"},
            "minItems": 1, "maxItems": 5
          }
        },
        "required": ["overall_summary", "common_themes", "recommended_actions"],
        "additionalProperties": false
      }
    }
  }
}
EOF
)

jq -n --argjson count "$record_count" --argjson report "$report" \
  '{input_count: $count} + $report'
