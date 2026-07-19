curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": true,
  "messages": [
    { "role": "user",
      "content": "Explain the Unix-Pipe in one single sentence with less than 16 words." }
  ]
}
EOF
