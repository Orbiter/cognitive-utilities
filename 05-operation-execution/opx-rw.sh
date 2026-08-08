#!/usr/bin/env bash
# execute approved commands and workspace file reads/writes to answer a request
# usage: echo "Read notes.txt and write a summary to report.md." | ./opx-rw.sh [-y]

set -uo pipefail

approve_all=false
case "$#:${1:-}" in
  0:) ;;
  1:-y) approve_all=true ;;
  *) echo "Usage: <prompt> | ./opx-rw.sh [-y]" >&2; exit 1 ;;
esac

workspace_root=$(pwd -P)

# Send the current conversation and available tools to the model.
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

# Ask before the model may inspect or change the local system.
approve() {
  [[ "$approve_all" == true ]] && return 0
  printf 'Tool request: %s\nApprove? [Y/n]: ' "$1" >/dev/tty
  IFS= read -r reply </dev/tty && [[ "$reply" =~ ^([Yy]([Ee][Ss])?)?$ ]]
}

# Reject absolute paths and lexical attempts to leave the workspace.
valid_relative_path() {
  case "$1" in
    ""|/*|..|../*|*/../*|*/..) return 1 ;;
    *) return 0 ;;
  esac
}

# Execute one approved command and return a structured tool result.
run_bash() {
  local command="$1" output exit_code
  case "$command" in
    ""|*'|'*|*';'*|*'&'*|*'>'*|*'<'*|*$'\n'*|*$'\r'*)
      jq -cn '{exit_code:1,output:"Rejected: use one command without pipes, redirections, separators, or newlines."}'
      return
      ;;
  esac
  if ! approve "bash $command"; then
    jq -cn '{exit_code:1,output:"Rejected by user."}'
    return
  fi
  output=$(bash -c "$command" 2>&1)
  exit_code=$?
  jq -cn --argjson exit_code "$exit_code" --arg output "$output" \
    '{exit_code:$exit_code,output:$output}'
}

# Read at most the first 200 lines of one approved workspace file.
run_read_file() {
  local path="$1" target directory output exit_code
  if ! valid_relative_path "$path"; then
    jq -cn '{exit_code:1,output:"Rejected: path must stay inside the workspace."}'
    return
  fi
  target="$workspace_root/$path"
  if [[ ! -f "$target" || -L "$target" ]]; then
    jq -cn '{exit_code:1,output:"Rejected: path must name a regular, non-symbolic file."}'
    return
  fi
  directory=$(cd -- "$(dirname -- "$target")" && pwd -P) || {
    jq -cn '{exit_code:1,output:"Rejected: file directory cannot be resolved."}'
    return
  }
  if [[ "$directory" != "$workspace_root" && "$directory" != "$workspace_root/"* ]]; then
    jq -cn '{exit_code:1,output:"Rejected: resolved path leaves the workspace."}'
    return
  fi
  if ! approve "read_file $path"; then
    jq -cn '{exit_code:1,output:"Rejected by user."}'
    return
  fi
  output=$(sed -n '1,200p' "$target" 2>&1)
  exit_code=$?
  jq -cn --argjson exit_code "$exit_code" --arg output "$output" \
    '{exit_code:$exit_code,output:$output}'
}

# Replace one approved workspace-relative file with exact content.
run_write_file() {
  local path="$1" content="$2" target parent ancestor directory output exit_code
  if ! valid_relative_path "$path"; then
    jq -cn '{exit_code:1,output:"Rejected: path must stay inside the workspace."}'
    return
  fi
  target="$workspace_root/$path"
  if [[ -L "$target" ]]; then
    jq -cn '{exit_code:1,output:"Rejected: target must not be a symbolic link."}'
    return
  fi
  parent=$(dirname -- "$target")
  ancestor="$parent"
  while [[ ! -e "$ancestor" ]]; do
    ancestor=$(dirname -- "$ancestor")
  done
  directory=$(cd -- "$ancestor" && pwd -P) || {
    jq -cn '{exit_code:1,output:"Rejected: target directory cannot be resolved."}'
    return
  }
  if [[ "$directory" != "$workspace_root" && "$directory" != "$workspace_root/"* ]]; then
    jq -cn '{exit_code:1,output:"Rejected: resolved path leaves the workspace."}'
    return
  fi
  if ! approve "write_file $path"; then
    jq -cn '{exit_code:1,output:"Rejected by user."}'
    return
  fi
  output=$({ mkdir -p "$(dirname "$target")" && printf '%s' "$content" >"$target"; } 2>&1)
  exit_code=$?
  [[ "$exit_code" -ne 0 ]] || output="Wrote $path"
  jq -cn --argjson exit_code "$exit_code" --arg output "$output" \
    '{exit_code:$exit_code,output:$output}'
}

# Turn the complete input stream into the initial conversation.
messages=$(jq -n --arg prompt "$(cat)" '[
  {"role":"system","content":"You are a coding assistant working in the current directory. Use exactly one tool per response until the task is complete. Use read_file for file contents, bash for inspection or tests, and write_file for file changes. Give a short final answer."},
  {"role":"user","content":$prompt}
]')

# Describe the three operations the model may request.
tools='[
  {"type":"function","function":{"name":"bash","description":"Run one shell command.","parameters":{"type":"object","properties":{"command":{"type":"string","description":"One command without pipes, redirections, separators, or newlines."}},"required":["command"],"additionalProperties":false},"strict":true}},
  {"type":"function","function":{"name":"read_file","description":"Read the first 200 lines of a workspace file.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"Workspace-relative path to a regular file."}},"required":["path"],"additionalProperties":false},"strict":true}},
  {"type":"function","function":{"name":"write_file","description":"Replace a workspace file with exact content.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"Workspace-relative file path."},"content":{"type":"string","description":"Complete file content."}},"required":["path","content"],"additionalProperties":false},"strict":true}}
]'

# Continue until the model answers without requesting another operation.
answer=$(llm)
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  name=$(jq -r '.function.name' <<<"$call")
  arguments=$(jq -r '.function.arguments' <<<"$call")

  case "$name" in
    bash)
      if command=$(jq -er '.command' <<<"$arguments"); then
        result=$(run_bash "$command")
      else
        result='{"exit_code":1,"output":"Invalid bash arguments."}'
      fi
      ;;
    read_file)
      if path=$(jq -er '.path' <<<"$arguments"); then
        result=$(run_read_file "$path")
      else
        result='{"exit_code":1,"output":"Invalid read_file arguments."}'
      fi
      ;;
    write_file)
      if path=$(jq -er '.path' <<<"$arguments") &&
         content=$(jq -er '.content' <<<"$arguments"); then
        result=$(run_write_file "$path" "$content")
      else
        result='{"exit_code":1,"output":"Invalid write_file arguments."}'
      fi
      ;;
    *) result='{"exit_code":1,"output":"Unknown tool."}' ;;
  esac

  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
    '. + [$assistant,{"role":"tool","tool_call_id":$id,"content":$result}]' <<<"$messages")
  answer=$(llm)
done

# Print the final answer for humans or the next pipeline stage.
jq -er '.choices[0].message.content' <<<"$answer"
