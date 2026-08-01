#!/usr/bin/env bash
# chat dialog, with system prompt, assistant response and second prompt
# usage: ./context.sh

curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    { "role": "system",
      "content": "Every answer must have less than 16 words." },
    { "role": "user",
      "content": "Explain the Unix-Pipe in one single sentence." },
    { "role": "assistant", 
      "content": "Unix-pipes let programs pass data streams to each other directly." },
    { "role": "user",
      "content": "What type of script would be a 'cognitive pipe'?" }
  ]
}
EOF
