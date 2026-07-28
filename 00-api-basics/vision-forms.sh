# vision request with forms and schema
# image from https://unsplash.com/de/fotos/mann-der-an-einem-uberfullten-schreibtisch-mit-einem-computer-arbeitet-BJHESX8uBS8

image_path="images/t-penguin-BJHESX8uBS8-unsplash.jpg"
base64_image=$(base64 < "$image_path" | tr -d '\n')

curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq '.choices[0].message.content | fromjson'
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    {"role": "user", "content": [
      {"type": "text", "text": "list 10 objects that are important to the man"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,$base64_image"}}
    ]}
  ],
  "response_format": { "type": "json_schema",
    "json_schema": { "strict": true,
      "schema": {
        "type": "array", "items": {"type": "string"},
        "minItems": 10, "maxItems": 10
      }
    }
  }
}
EOF
