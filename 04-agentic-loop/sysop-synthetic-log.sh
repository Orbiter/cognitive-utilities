#!/usr/bin/env bash
# investigate logs until the root cause is found
# usage: echo "Diagnose incident INC-781." | ./sysop-synthetic-log.sh
set -euo pipefail

logs='application.log: incident=INC-781 status=unresolved next_id=db-42
database.log: incident=db-42 status=unresolved next_id=fs-9
system.log: incident=fs-9 status=resolved root_cause="/var/lib is 100% full"'

# tool: lookup a line in the (synthetic) log
lookup() {
  grep -iF -- "incident=$1 " <<<"$logs" || true
}

# call the llm
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

# initiate messages and attach tool description
messages=$(jq -n --arg prompt "$(cat)" '[
  {"role":"system","content":"Diagnose the incident. If a lookup returns status=unresolved, respond only with another lookup using next_id. Answer only after status=resolved, then give the complete chain."},
  {"role":"user","content":$prompt}
]')
tools='[{"type":"function","function":{
  "name":"lookup","description":"Look up exactly one diagnostic incident.",
  "parameters":{"type":"object","properties":{"id":{"type":"string","description":"Incident ID from the prompt or a next field."}},
  "required":["id"],"additionalProperties":false},"strict":true
}}]'

# get first answer
answer=$(llm)

# loop until no more tool call is submitted
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  id=$(jq -r '.function.arguments | fromjson | .id' <<<"$call")
  result=$(lookup "$id")
  echo "# Tool Call: lookup \"$id\""

  # extend message list with tool result
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":"lookup","content":$result}]' <<<"$messages")
  answer=$(llm)
done

# show / pipe the answer
jq -er '.choices[0].message.content' <<<"$answer"
