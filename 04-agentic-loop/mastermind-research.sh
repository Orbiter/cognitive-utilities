#!/usr/bin/env bash
# autonomous research: discover a hidden four-bit code
# usage: echo "Find the hidden code." | ./mastermind-research.sh
set -euo pipefail

secret=1011

# Return how many bits are in the correct position.
experiment() {
  local guess=$1 exact=0 first_wrong=null next_guess= replacement evidence i
  [[ "$guess" =~ ^[01]{4}$ ]] || {
    jq -cn '{error:"Use exactly four binary digits."}'
    return
  }

  for i in 0 1 2 3; do
    if [[ ${guess:i:1} == "${secret:i:1}" ]]; then
      ((exact += 1))
    elif [[ $first_wrong == null ]]; then
      first_wrong=$((i + 1))
      replacement=$((1 - ${guess:i:1}))
      next_guess="${guess:0:i}${replacement}${guess:$((i + 1))}"
      evidence="Position $first_wrong, counted from the left, is the first mismatch. The guessed bit ${guess:i:1} must therefore be $replacement. Test $next_guess next."
    fi
  done

  [[ $first_wrong != null ]] || \
    evidence="All four positions match, so $guess is the hidden code."

  jq -cn --arg guess "$guess" --argjson exact "$exact" \
    --argjson first_wrong "$first_wrong" --arg next_guess "$next_guess" --arg evidence "$evidence" \
    '{guess:$guess,correct_positions:$exact,first_wrong_position:$first_wrong,
      next_guess:(if $next_guess == "" then null else $next_guess end),evidence:$evidence}'
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

system_prompt='You are researching a hidden four-bit binary code.
Make exactly one experiment per response.
Start with 0000.
After every result, pass next_guess unchanged to the next experiment.
Do not invent or calculate another guess.
When next_guess is null, the tested guess is the solution.

In the final answer:
- list every guess with correct_positions;
- reproduce its evidence in order; and
- state the confirmed code.

Positions are always counted from the left.
Do not introduce another indexing scheme or speculate beyond the tool evidence.'

messages=$(jq -n --arg system_prompt "$system_prompt" --arg prompt "$(cat)" '[
  {"role":"system","content":$system_prompt},
  {"role":"user","content":$prompt}
]')
tools='[{"type":"function","function":{
  "name":"experiment",
  "description":"Test one possible four-bit binary code and count exact positional matches.",
  "parameters":{"type":"object","properties":{
    "guess":{"type":"string","enum":["0000","0001","0010","0011","0100","0101","0110","0111","1000","1001","1010","1011","1100","1101","1110","1111"]}
  },"required":["guess"],"additionalProperties":false},"strict":true
}}]'

answer=$(llm)
experiments=0

while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  ((experiments += 1))
  ((experiments <= 6)) || { echo "Error: experiment limit reached" >&2; exit 1; }
  guess=$(jq -er '.function.arguments | fromjson | .guess' <<<"$call")
  observation=$(experiment "$guess")
  echo "# Experiment $experiments: $observation"
  
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg observation "$observation" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":"experiment","content":$observation}]' <<<"$messages")
  answer=$(llm)
done

jq -er '.choices[0].message.content' <<<"$answer"
