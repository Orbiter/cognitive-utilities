#!/usr/bin/env bash
# calculator filter: question to calculated answer
# usage: echo "How many seconds are there in 17 days?" | ./calculator.sh
# usage: echo "Three little pigs built a house? Which one survives?" | ./calculator.sh
set -euo pipefail

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

messages=$(jq -n --arg prompt "$(cat)" '[
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
# A tool call is optional, see if the calculator tool was called:
if call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); then
  term=$(jq -er '.function.arguments | fromjson | .term' <<<"$call")

  # Python Guardrails: Allow only arithmetic syntax before evaluating the term.
  result=$(python3 -c 'import ast,sys
t=ast.parse(sys.argv[1],mode="eval")
ok=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,ast.Pow,ast.UAdd,ast.USub)
assert all(isinstance(n,ok) and (not isinstance(n,ast.Constant) or type(n.value) in (int,float)) for n in ast.walk(t))
print(eval(compile(t,"","eval"),{"__builtins__":{}}))' "$term")

  # Debug: show that the tool call has happened
  echo "# Tool Call: compute '$term' = $result"

  # Add the call and its result, then ask for the final answer.
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":"calculator","content":$result}]' <<<"$messages")
  tools='[]'
  answer=$(llm)
fi

# Print only the assistant's answer.
jq -er '.choices[0].message.content' <<<"$answer"
