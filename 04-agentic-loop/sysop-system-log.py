#!/usr/bin/env bash
# investigate real system logs with at most 20 tool calls
# usage: echo "Inspect /var/log and report recent errors. Make a full audit." | ./sysop-system-log.py
set -euo pipefail

log_root=$(realpath /var/log)

# guardrail for path variables
safe_path() {
  local path
  path=$(realpath "$1" 2>/dev/null) || return 1
  [[ "$path" == "$log_root" || "$path" == "$log_root/"* ]] || return 1
  printf '%s\n' "$path"
}

# tool: list files in a given directory path
list() {
  local directory
  directory=$(safe_path "$1") || { echo "Error: directory outside /var/log"; return; }
  [[ -d "$directory" ]] || { echo "Error: not a directory"; return; }
  find "$directory" -maxdepth 1 -mindepth 1 -print 2>/dev/null \
    | sed "s|^$log_root|/var/log|" | head -50
}

# tool: search for content in a given file path
lookup() {
  local path
  path=$(safe_path "$1") || { echo "Error: file outside /var/log"; return; }
  [[ -f "$path" ]] || { echo "Error: not a file"; return; }
  case "$path" in
    *.gz) gzip -cd -- "$path" | grep -iF -m 20 -- "$2" || true ;;
    *) grep -iF -m 20 -- "$2" "$path" 2>&1 || true ;;
  esac
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
  {"role":"system","content":"You are a system operator. Investigate /var/log until you can answer. Use list only for directories and lookup only for files. Never repeat a tool call. Give a short, evidence-based answer."},
  {"role":"user","content":$prompt}
]')
tools='[
  {"type":"function","function":{
    "name":"list","description":"List up to 50 entries in a directory below /var/log.",
    "parameters":{"type":"object","properties":{"directory":{"type":"string","description":"Directory path below /var/log."}},
    "required":["directory"],"additionalProperties":false},"strict":true
  }},
  {"type":"function","function":{
    "name":"lookup","description":"Search one plain or .gz log below /var/log for one literal text.",
    "parameters":{"type":"object","properties":{
      "path":{"type":"string","description":"Log file path returned by list."},
      "query":{"type":"string","description":"One literal text, not a regular expression. Use separate calls for alternatives."}
    },"required":["path","query"],"additionalProperties":false},"strict":true
  }}
]'

# initiate guardrails
calls=0
seen_calls=''

# get first answer
answer=$(llm)

# loop until no more tool call is submitted
while jq -e '.choices[0].message.tool_calls | length > 0' <<<"$answer" >/dev/null; do
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    '. + [$assistant]' <<<"$messages")

  # check guardrails and make tool call
  duplicate_call=false
  while IFS= read -r call; do
    ((calls += 1))
    ((calls <= 20)) || { echo "Error: tool call limit reached" >&2; exit 1; }
    name=$(jq -r '.function.name' <<<"$call")
    arguments=$(jq -r '.function.arguments' <<<"$call")
    key=$(jq -cnS --arg name "$name" --argjson arguments "$arguments" \
      '{name:$name,arguments:$arguments}')
    if grep -Fqx -- "$key" <<<"$seen_calls"; then
      result="Error: duplicate tool call. Finish with the evidence already collected."
      duplicate_call=true
    else
      seen_calls+="$key"$'\n'
      case "$name" in
        list) result=$(list "$(jq -r '.directory' <<<"$arguments")") ;;
        lookup) result=$(lookup "$(jq -r '.path' <<<"$arguments")" \
          "$(jq -r '.query' <<<"$arguments")") ;;
        *) result="Error: unknown tool '$name'" ;;
      esac
    fi
    echo "# Tool Call $calls: $name $arguments"

    # extend message list with tool result
    messages=$(jq --arg id "$(jq -r '.id' <<<"$call")" \
      --arg name "$name" --arg result "$result" \
      '. + [{"role":"tool","tool_call_id":$id,"name":$name,"content":$result}]' <<<"$messages")
  done < <(jq -c '.choices[0].message.tool_calls[]' <<<"$answer")

  # A repeated call means the investigation is stuck. Force a final answer.
  if [[ "$duplicate_call" == true ]]; then
    tools='[]'
  fi
  answer=$(llm)
done

# show / pipe the answer
jq -er '.choices[0].message.content' <<<"$answer"
