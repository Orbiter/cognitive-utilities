#!/usr/bin/env bash
# simple filter example: text to bug|feature|question|other
# usage: echo 'The application crashes during startup.' | ./choice-openai.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    {"role": "system", "content": "Classify the input. Estimate the probability of each category so the probabilities sum to 1. Set choice to the category with the highest probability."},
    {"role": "user", "content": $input_json}
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": { "name": "classification", "strict": true,
      "schema": { "type": "object",
        "properties": {
          "choice": {"type": "string", "enum": ["bug", "feature", "question", "other"]},
          "probabilities": {
            "type": "object",
            "properties": {
              "bug": {"type": "number", "minimum": 0, "maximum": 1},
              "feature": {"type": "number", "minimum": 0, "maximum": 1},
              "question": {"type": "number", "minimum": 0, "maximum": 1},
              "other": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["bug", "feature", "question", "other"], "additionalProperties": false
          },
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["choice", "probabilities", "confidence"], "additionalProperties": false
      }
    }
  }
}
EOF
