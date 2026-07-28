#!/usr/bin/env bash
# repository detective: answer questions about the files in the repository ( with up to two tool calls)
# zero calls:         echo "What is a README file?" | ./inspect.sh
# one find_file call: echo "Which bash file contains 'Python Guardrails'?" | ./inspect.sh
# one read_file call: echo "Summarize the README.md." | ./inspect.sh
# two calls:          echo "Find the bash file containing 'Python Guardrails', read it, and explain it." | ./inspect.sh
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

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

find_file() {
  local query=$1
  rg -l -F -- "$query" "$repo_root" 2>/dev/null \
    | sed "s|^$repo_root/||" | head -10 || true
}

read_file() {
  local path=$1 directory target
  [[ "$path" != /* ]] || { echo "Error: path must be relative"; return; }
  target="$repo_root/$path"
  [[ -f "$target" && ! -L "$target" ]] ||
    { echo "Error: file not found"; return; }
  directory=$(cd "$(dirname "$target")" && pwd -P)
  [[ "$directory/" == "$repo_root/"* ]] ||
    { echo "Error: path outside repository"; return; }
  sed -n '1,200p' "$target"
}

run_tool() {
  local name=$1 arguments=$2
  case "$name" in
    find_file) find_file "$(jq -r '.query' <<<"$arguments")" ;;
    read_file) read_file "$(jq -r '.path' <<<"$arguments")" ;;
    *) echo "Error: unknown tool '$name'" ;;
  esac
}

messages=$(jq -n --arg prompt "$(cat)" '[
  {"role":"system","content":"You are a repository detective. Use at most two tool calls. Use find_file to discover a path and read_file to inspect a known path. Give only very short answers."},
  {"role":"user","content":$prompt}
]')

tools='[
  {"type":"function","function":{
    "name":"find_file","description":"Find up to ten repository files containing an exact text.",
    "parameters":{"type":"object","properties":{"query":{"type":"string","description":"Exact text to find."}},
    "required":["query"],"additionalProperties":false},"strict":true
  }},
  {"type":"function","function":{
    "name":"read_file","description":"Read the first 200 lines of a known repository file.",
    "parameters":{"type":"object","properties":{"path":{"type":"string","description":"Repository-relative file path."}},
    "required":["path"],"additionalProperties":false},"strict":true
  }}
]'

answer=$(llm)
# Zero, one, or two tool calls are enough for this detective.
for step in 1 2; do
  call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer") || break
  name=$(jq -r '.function.name' <<<"$call")
  arguments=$(jq -r '.function.arguments' <<<"$call")
  result=$(run_tool "$name" "$arguments")

  echo "# Tool Call $step: $name $arguments"
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg name "$name" --arg result "$result" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":$name,"content":$result}]' <<<"$messages")
  answer=$(llm)
done

jq -er '.choices[0].message.content' <<<"$answer"
