#!/usr/bin/env bash
# git historian: answer questions about this repository's history (with up to two tool calls)
# We provide two tools: git_log and git_show
# zero calls:         echo "What is a Git commit?" | ./history.sh
# one git_log call:   echo "What are the latest commits in this repository?" | ./history.sh
# one git_show call:  echo "Summarize commit 182b60b." | ./history.sh
# two calls:          echo "Find the commit that added the basic LLM shell examples and explain what it changed." | ./history.sh
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

git_log() {
  local query=$1
  if [[ -n "$query" ]]; then
    git -C "$repo_root" log -10 --format='%h %ad %s' --date=short \
      --regexp-ignore-case --grep="$query"
  else
    git -C "$repo_root" log -10 --format='%h %ad %s' --date=short
  fi
}

git_show() {
  local revision=$1 commit
  [[ "$revision" =~ ^[0-9a-fA-F]{4,40}$ ]] ||
    { echo "Error: revision must be a commit hash"; return; }
  commit=$(git -C "$repo_root" rev-parse --verify "${revision}^{commit}" 2>/dev/null) ||
    { echo "Error: commit not found"; return; }
  git -C "$repo_root" show --no-ext-diff --format=fuller --stat --patch "$commit" \
    | sed -n '1,200p'
}

run_tool() {
  local name=$1 arguments=$2
  case "$name" in
    git_log) git_log "$(jq -r '.query' <<<"$arguments")" ;;
    git_show) git_show "$(jq -r '.revision' <<<"$arguments")" ;;
    *) echo "Error: unknown tool '$name'" ;;
  esac
}

messages=$(jq -n --arg prompt "$(cat)" '[
  {"role":"system","content":"You are a Git historian. Use at most two tool calls. Use git_log to discover a commit and git_show to inspect a known commit hash. Give only very short answers."},
  {"role":"user","content":$prompt}
]')

tools='[
  {"type":"function","function":{
    "name":"git_log","description":"List up to ten commits, optionally filtered by text in the commit message.",
    "parameters":{"type":"object","properties":{"query":{"type":"string","description":"Text in the commit message, or an empty string for recent commits."}},
    "required":["query"],"additionalProperties":false},"strict":true
  }},
  {"type":"function","function":{
    "name":"git_show","description":"Show metadata, changed files, and the patch for a known commit hash.",
    "parameters":{"type":"object","properties":{"revision":{"type":"string","description":"A full or abbreviated hexadecimal commit hash."}},
    "required":["revision"],"additionalProperties":false},"strict":true
  }}
]'

answer=$(llm)
# Zero, one, or two tool calls are enough for this history.
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
