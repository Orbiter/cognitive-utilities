# simple chat request, result token streaming

curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": true,
  "messages": [
    { "role": "user",
      "content": "Explain the Unix-Pipe in one single sentence with less than 16 words." }
  ]
}
EOF
