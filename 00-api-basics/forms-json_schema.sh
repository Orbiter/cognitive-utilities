curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL",
  "temperature": 0.0, "reasoning_effort": "none", "stream": false,
  "messages": [
    { "role": "system", "content": "Translate into Spanish, and Italian. Generate JSON." },
    { "role": "user",   "content": "I love programming." }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": { "strict": true,
        "schema": { "type": "object",
          "properties": {
            "spanish": { "type": "string" }, "italian": { "type": "string" }
          },
          "required": ["spanish", "italian"]
        }
      }
  }
}
EOF
