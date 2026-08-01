#!/usr/bin/env bash
# form request, with prompt nudging only
# usage: ./forms-json_.sh

curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq '.choices[0].message.content'
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    { "role": "system", "content": "Translate into Spanish, and Italian. Generate JSON." },
    { "role": "user",   "content": "I love programming." }
  ]
}
EOF
