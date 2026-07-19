#!/usr/bin/env bash
# Usage: echo 'Invoice RE-2026-017 from Example GmbH: 149.90€.' | ./extract.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -e '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": false,
  "messages": [
    {"role": "system", "content": "Extract invoice fields from the input."},
    {"role": "user", "content": $input_json}
  ],
  "response_format": { "type": "json_schema",
    "json_schema": { "strict": true,
      "schema": { "type": "object",
        "properties": {
          "sender": {"type": ["string", "null"]},
          "invoice_number": {"type": ["string", "null"]},
          "amount": {"type": ["number", "null"]},
          "currency": {"type": ["string", "null"]}
        },
        "required": ["sender", "invoice_number", "amount", "currency"],
        "additionalProperties": false
      }
    }
  }
}
EOF
