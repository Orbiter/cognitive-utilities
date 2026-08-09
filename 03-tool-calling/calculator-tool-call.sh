#!/usr/bin/env bash
# calculator example: user asks for a calculation
# usage: ./calculator-tool-call.sh

prompt="How many seconds are there in 17 days?"

llm() {
  curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
    -d @- <<EOF
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": $messages, "tools": $tools
}
EOF
}

messages=$(jq -n --arg prompt "$prompt" '[
  {"role":"system","content":"Use the calculator tool for arithmetic calculations. Give short answers."},
  {"role":"user","content":$prompt}
]')

tools='[{"type":"function","function":{
  "name":"calculator","description":"Calculate an arithmetic expression with a Python function.",
  "parameters":{"type":"object","properties":{"term":{"type":"string",
  "description":"A Python-compatible arithmetic expression using numbers, parentheses, +, -, *, /, //, %, or **."}},
  "required":["term"],"additionalProperties":false},"strict":true
}}]'

answer=$(llm)
jq . <<<"$answer"
