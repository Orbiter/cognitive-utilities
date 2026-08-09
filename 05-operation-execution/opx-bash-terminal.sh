#!/usr/bin/env bash
# interactive, non-streaming Bash agent that retains the conversation history
# usage: ./opx-bash-terminal.sh

set -uo pipefail

llm() {
  curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d @- <<EOF
{
  "model": "$OPENAI_MODEL", "temperature": $OPENAI_TEMPERATURE,
  "reasoning_effort": "$OPENAI_REASONING_EFFORT", "stream": false,
  "messages": $messages, "tools": $tools
}
EOF
}

tool_result() {
  jq -cn --argjson exit_code "$1" --arg output "$2" \
    '{exit_code:$exit_code,output:$output}'
}

bash_permissions='{
  "*":"ask", "ls *":"allow", "pwd *":"allow", "cat *":"allow",
  "head *":"allow", "chmod *":"allow", "tail *":"allow", "wc *":"allow",
  "stat *":"allow", "file *":"allow", "mkdir *":"allow", "find *":"allow",
  "grep *":"allow", "rg *":"allow", "which *":"allow", "touch *":"allow",
  "whereis *":"allow", "env *":"allow", "printenv *":"allow", "ps *":"allow",
  "top *":"allow", "du *":"allow", "df *":"allow", "tree *":"allow",
  "git status *":"allow", "git diff *":"allow", "git log *":"allow",
  "git show*":"allow", "git rev-parse *":"allow", "git ls-files *":"allow"
}'

# Evaluate patterns in source order: the last matching rule wins.
permission_for() {
  local command="$1" pattern action decision=ask
  while IFS=$'\t' read -r pattern action; do
    [[ $command == $pattern ]] && decision=$action
  done < <(jq -r 'to_entries[] | [.key,.value] | @tsv' <<<"$bash_permissions")
  printf '%s' "$decision"
}

# Reject shell composition so one tool call remains one visible command.
valid_command() {
  case "$1" in
    ""|*'|'*|*';'*|*'&'*|*'>'*|*'<'*|*'$('*|*'`'*|*$'\n'*|*$'\r'*) return 1 ;;
    *) return 0 ;;
  esac
}

approve_command() {
  local command="$1" reply
  printf 'Approve Bash command? [Y/n]\n%s\n> ' "$command" >/dev/tty
  IFS= read -r reply </dev/tty && [[ $reply =~ ^([Yy]([Ee][Ss])?)?$ ]]
}

run_bash() {
  local command="$1" permission output exit_code

  if ! valid_command "$command"; then
    printf 'Policy: deny (syntax guard)\n' >&2
    tool_result 1 \
      'Rejected: use one command without pipes, redirections, separators, command substitutions, or newlines.'
    return
  fi

  permission=$(permission_for "$command")
  printf 'Policy: %s\n' "$permission" >&2
  case "$permission" in
    allow) ;;
    ask)
      approve_command "$command" || {
        tool_result 1 'Rejected by user.'
        return
      }
      ;;
    deny)
      tool_result 1 'Rejected by policy.'
      return
      ;;
    *)
      tool_result 1 'Rejected: invalid permission in Bash policy.'
      return
      ;;
  esac

  output=$(bash -c "$command" 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

system_prompt='You are a Linux system operator working in the current directory.
Use Bash to inspect or operate the system when that helps answer the request.

Tool behavior:
- You may request several independent Bash tool calls in one response.
- Submit exactly one command in each tool call.
- Pipes, redirections, separators, command substitutions, and newlines are rejected.
- An inline last-match-wins policy decides whether a command is allowed, denied, or requires approval.

Remember the complete conversation and use earlier results when answering later requests.
When the work is complete, give a short final answer.'

tools='[
  {
    "type": "function",
    "function": {
      "name": "bash",
      "description": "Run one guarded Bash command according to the inline allow, ask, or deny policy.",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {
            "type": "string",
            "description": "One command without pipes, redirections, separators, command substitutions, or newlines."
          }
        },
        "required": ["command"],
        "additionalProperties": false
      },
      "strict": true
    }
  }
]'

messages=$(jq -n --arg system_prompt "$system_prompt" '[
  {"role":"system","content":$system_prompt}
]')

printf "OPX Bash Terminal (exit with 'exit', 'quit', or 'ende')\n\n"

while true; do
  printf 'Prompt: '
  if ! IFS= read -r prompt; then
    printf '\n'
    break
  fi

  [[ -n ${prompt//[[:space:]]/} ]] || continue
  normalized=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')
  case "$normalized" in exit|quit|ende) break ;; esac

  # Extend the persistent context with this conversation turn.
  messages=$(jq --arg prompt "$prompt" '. + [{"role":"user","content":$prompt}]' \
    <<<"$messages")

  if ! answer=$(llm); then
    messages=$(jq '.[0:-1]' <<<"$messages")
    printf '\nError: LLM request failed.\n\n' >&2
    continue
  fi

  # Run the agentic tool loop for this conversation turn.
  while jq -e '.choices[0].message.tool_calls | length > 0' >/dev/null <<<"$answer"; do
    assistant=$(jq '.choices[0].message' <<<"$answer")
    messages=$(jq --argjson assistant "$assistant" '. + [$assistant]' <<<"$messages")

    while IFS= read -r call; do
      name=$(jq -r '.function.name' <<<"$call")
      arguments=$(jq -r '.function.arguments' <<<"$call")
      printf 'Tool: %s %s\n' "$name" "$arguments" >&2

      case "$name" in
        bash)
          if command=$(jq -er '.command' <<<"$arguments"); then
            result=$(run_bash "$command")
          else
            result=$(tool_result 1 'Invalid bash arguments.')
          fi
          ;;
        *)
          result=$(tool_result 1 'Unknown tool.')
          ;;
      esac

      messages=$(jq --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
        '. + [{"role":"tool","tool_call_id":$id,"content":$result}]' <<<"$messages")
    done < <(jq -c '.choices[0].message.tool_calls[]' <<<"$answer")

    if ! answer=$(llm); then
      printf '\nError: LLM request failed after a tool call.\n\n' >&2
      answer=
      break
    fi
  done

  [[ -n $answer ]] || continue
  if response=$(jq -er '.choices[0].message.content' <<<"$answer"); then
    printf '\nAnswer: %s\n\n' "$response"
    messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
      '. + [$assistant]' <<<"$messages")
  else
    printf '\nError: LLM returned no final answer.\n\n' >&2
  fi
done
