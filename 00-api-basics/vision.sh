# simple vision request
# image from https://unsplash.com/de/fotos/mann-der-an-einem-uberfullten-schreibtisch-mit-einem-computer-arbeitet-BJHESX8uBS8

image_path="images/t-penguin-BJHESX8uBS8-unsplash.jpg"
base64_image=$(base64 < "$image_path" | tr -d '\n')

curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq '.choices[0].message'
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": [
    { "role": "system",
      "content": "Every answer must have less than 16 words." },
    {"role": "user", "content": [
      {"type": "text", "text": "Explain whats in the image."},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,$base64_image"}}
    ]}
  ]
}
EOF
