#!/usr/bin/env bash
# calculator example: assistant response after a calculation
# usage: ./calculator-tool-response.sh

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
  {"role":"user","content":$prompt},
  {"role":"assistant","content":"","tool_calls":[{
    "id":"call_calculator","type":"function",
    "function":{"name":"calculator","arguments":"{\"term\":\"17 * 24 * 60 * 60\"}"}
  }]},
  {"role":"tool","tool_call_id":"call_calculator","name":"calculator","content":"1468800"}
]')

tools='[{"type":"function","function":{
  "name":"calculator","description":"Calculate an arithmetic expression with a Python function.",
  "parameters":{"type":"object","properties":{"term":{"type":"string",
  "description":"A Python-compatible arithmetic expression using numbers, parentheses, +, -, *, /, //, %, or **."}},
  "required":["term"],"additionalProperties":false},"strict":true
}}]'

answer=$(llm)
jq . <<<"$answer"
