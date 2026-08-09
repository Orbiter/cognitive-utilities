#!/usr/bin/env bash
# home assistant example: user request to switch on the light
# usage: ./basic-tool-call.sh

curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
      {"role": "system", "content": "You are a home assistant."},
      {"role": "user", "content": "Switch on the light"}
    ],
    "tools": [{
      "type": "function",
      "function": {
        "name": "lightswitch", "description": "With this tool you can switch on the light",
        "parameters": {
          "type": "object", "properties": {
            "switch": { "type": "boolean", "description": "true for on, false for off" }
          },
          "required": [ "switch" ], "additionalProperties": false
        }, "strict": true
      }
     }]
  }
}
EOF