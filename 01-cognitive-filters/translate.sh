#!/usr/bin/env bash
# Usage: echo 'The build completed successfully.' | ./translate.sh de
set -euo pipefail

if (( $# != 1 )); then
  echo "Usage: $0 TARGET_LANGUAGE" >&2
  exit 2
fi
target_language=$1

input=$(cat)
if [[ -z "${input//[[:space:]]/}" ]]; then
  echo "translate.sh: expected text on stdin" >&2
  exit 1
fi
input_json=$(jq -Rn --arg value "$input" '$value')
instruction=$(printf 'Translate the input to %s.' "$target_language")
instruction_json=$(jq -Rn --arg value "$instruction" '$value')

curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.choices[0].message.content | fromjson | .translation'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none",
  "stream": false,
  "messages": [
    {"role": "system", "content": $instruction_json},
    {"role": "user", "content": $input_json}
  ],
  "response_format": { "type": "json_schema",
    "json_schema": { "strict": true,
      "schema": { "type": "object",
        "properties": {
          "translation": {"type": "string"}
        },
        "required": ["translation"],
        "additionalProperties": false
      }
    }
  }
}
EOF
