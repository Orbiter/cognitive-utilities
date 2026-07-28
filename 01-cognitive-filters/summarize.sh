#!/usr/bin/env bash
# simple tl;dr generator: text to short text
# usage: cat README.md | ./summarize.sh
set -euo pipefail

input_json=$(jq -Rn --arg value "$(cat)" '$value')

curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.choices[0].message.content | fromjson | .summary' | fold -s -w 75
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    {"role": "system", "content": "Summarize the input in its original language in no more than three concise sentences."},
    {"role": "user", "content": $input_json}
  ],
  "response_format": { "type": "json_schema",
    "json_schema": { "strict": true,
      "schema": { "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"], "additionalProperties": false
      }
    }
  }
}
EOF
