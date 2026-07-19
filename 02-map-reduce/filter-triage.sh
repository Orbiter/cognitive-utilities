#!/usr/bin/env bash
# Usage: ./map-lines.sh < issues.txt | ./filter-triage.sh
set -euo pipefail

line_number=0
while IFS= read -r line || [[ -n "$line" ]]; do
  ((line_number += 1))
  record=$(jq -ce '
    if type == "object" and (.text | type == "string") then .
    else error("expected an object with a string field named text")
    end
  ' <<<"$line") || {
    echo "filter-triage.sh: invalid record on line $line_number" >&2
    exit 1
  }
  record_json=$(jq -Rn --arg value "$record" '$value')

  triage=$(curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
    -d @- <<EOF | jq -ec '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": false,
  "messages": [
    {"role": "system", "content": "Triage the issue in the JSON object. Base every field only on its text value."},
    {"role": "user", "content": $record_json}
  ],
  "response_format": {"type": "json_schema",
    "json_schema": {"strict": true,
      "schema": {"type": "object",
        "properties": {
          "category": {"type": "string", "enum": ["bug", "feature", "question", "other"]},
          "priority": {"type": "string", "enum": ["low", "medium", "high"]},
          "summary": {"type": "string"},
          "route": {"type": "string", "enum": ["engineering", "product", "support", "manual-review"]}
        },
        "required": ["category", "priority", "summary", "route"],
        "additionalProperties": false
      }
    }
  }
}
EOF
  )

  jq -cn --argjson record "$record" --argjson triage "$triage" \
    '$record + $triage'
done
