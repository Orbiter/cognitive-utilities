#!/usr/bin/env bash
# Usage: echo 'The application crashes during startup.' | ./classify.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.choices[0].message.content | fromjson | .category'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": false,
  "messages": [
    {"role": "system", "content": "Classify the input."},
    {"role": "user", "content": $input_json}
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": { "strict": true,
      "schema": { "type": "object",
        "properties": {
          "category": {"type": "string", "enum": ["bug", "feature", "question", "other"]}
        },
        "required": ["category"], "additionalProperties": false
      }
    }
  }
}
EOF
