#!/usr/bin/env bash
# autonomous research: discover a hidden cellular automaton rule
# usage: echo "Determine the hidden Wolfram rule." | ./research.sh
set -euo pipefail

rule=30

# An elementary cellular automaton updates each cell from its left neighbor,
# its own state, and its right neighbor. These three bits form one of eight
# neighborhoods from 000 to 111. A Wolfram rule assigns the next center-cell
# state to each neighborhood; the eight output bits form a number from 0 to 255.
# One experiment applies the hidden rule to one neighborhood and observes its
# output bit. Testing all eight neighborhoods reveals the complete rule.
experiment() {
  local pattern=$1
  [[ "$pattern" =~ ^[01]{3}$ ]] ||
    { echo "Error: the neighborhood must contain exactly three bits"; return; }
  printf 'observation: %s -> %d\n' "$pattern" "$((rule >> 2#$pattern & 1))"
}

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
  {"role":"system","content":"You are an autonomous researcher studying a black-box elementary cellular automaton. Conduct exactly one experiment per response. Determine all eight neighborhood observations before concluding. Interpret outputs for 111 through 000 as a binary Wolfram rule number. Your final report must use the headings Thesis, Experiments, Observations, Derivation, and Conclusion."},
  {"role":"user","content":$prompt}
]')
tools='[{"type":"function","function":{
  "name":"experiment",
  "description":"Observe the next center-cell state for one neighborhood of a hidden elementary cellular automaton.",
  "parameters":{"type":"object","properties":{
    "neighborhood":{"type":"string","enum":["000","001","010","011","100","101","110","111"],
    "description":"Exactly one three-bit neighborhood to test."}
  },"required":["neighborhood"],"additionalProperties":false},"strict":true
}}]'

answer=$(llm)
experiments=0

# Continue the study until the researcher submits its conclusion.
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  ((experiments += 1))
  ((experiments <= 20)) || { echo "Error: experiment limit reached" >&2; exit 1; }
  neighborhood=$(jq -r '.function.arguments | fromjson | .neighborhood' <<<"$call")
  observation=$(experiment "$neighborhood")
  echo "# Experiment $experiments: $observation"

  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg observation "$observation" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":"experiment","content":$observation}]' <<<"$messages")
  answer=$(llm)
done

jq -er '.choices[0].message.content' <<<"$answer"
