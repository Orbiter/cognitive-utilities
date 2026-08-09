#!/usr/bin/env bash
# agentic loop with list_files, read_file, and write_file tools
# usage: echo "Read notes.txt and write a summary to report.md." | ./opx-rw.sh
#
# examples:
# echo "List the files in this directory and explain what this project contains." | ./opx-rw.sh
# echo "Read README.md and summarize the workshop in five bullet points." | ./opx-rw.sh
# echo "Read notes.txt and create a new file named notes-summary.txt with a summary." | ./opx-rw.sh
# echo "List the files, inspect the shell scripts, and report which tools they require." | ./opx-rw.sh
# echo "understand the content of this directory and write a content.md" | ./opx-rw.sh

set -uo pipefail

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

tool_result() {
  jq -cn --argjson exit_code "$1" --arg output "$2" \
    '{exit_code:$exit_code,output:$output}'
}

list_files() {
  local output exit_code
  output=$(ls -la 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

read_file() {
  local output exit_code
  if [[ $1 == */* ]]; then
    tool_result 1 'Rejected: filename must not contain /.'
    return
  fi
  output=$(cat -- "$1" 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

write_file() {
  local output exit_code
  if [[ $1 == */* ]]; then
    tool_result 1 'Rejected: filename must not contain /.'
    return
  fi
  if [[ -e $1 || -L $1 ]]; then
    tool_result 1 'Rejected: file already exists.'
    return
  fi
  output=$({ set -o noclobber; printf '%s' "$2" >"$1"; } 2>&1)
  exit_code=$?
  [[ $exit_code -ne 0 ]] || \
    output="Created $1. write_file has now been used; finish with a final answer."
  tool_result "$exit_code" "$output"
}

system_prompt='You are a coding assistant working in the current directory.

Available tools:
- Use list_files to inspect the current directory.
- Use read_file to read file contents.
- Use write_file to create one new file.

Limits:
- Call list_files at most once.
- Call write_file at most once.
- After receiving any write_file result, finish with a short final answer.'

messages=$(jq -n --arg system_prompt "$system_prompt" --arg prompt "$(cat)" '[
  {"role":"system","content":$system_prompt},
  {"role":"user","content":$prompt}
]')

tools='[
  {
    "type": "function",
    "function": {
      "name": "list_files",
      "description": "List the current directory with ls -la. This tool can be called only once.",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": false
      },
      "strict": true
    }
  },
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read a complete file from the current directory. The filename must not contain /.",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {
            "type": "string",
            "description": "A file name without /."
          }
        },
        "required": ["filename"],
        "additionalProperties": false
      },
      "strict": true
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_file",
      "description": "Create one new file in the current directory. This tool can be called only once; finish with a final answer afterward. Existing files are rejected and the filename must not contain /.",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {
            "type": "string",
            "description": "A new file name without /. It must not already exist."
          },
          "content": {
            "type": "string"
          }
        },
        "required": ["filename", "content"],
        "additionalProperties": false
      },
      "strict": true
    }
  }
]'

# start the agentic loop
answer=$(llm)
list_files_used=false
write_file_used=false
while jq -e '.choices[0].message.tool_calls | length > 0' >/dev/null <<<"$answer"; do
  assistant=$(jq '.choices[0].message' <<<"$answer")
  messages=$(jq --argjson assistant "$assistant" '. + [$assistant]' <<<"$messages")

  # process tool calls
  while IFS= read -r call; do
    name=$(jq -r '.function.name' <<<"$call")
    arguments=$(jq -r '.function.arguments' <<<"$call")
    if [[ $name == write_file ]]; then
      printf 'Tool: write_file %s\n' "$(jq -c '{filename}' <<<"$arguments")" >&2
    else
      printf 'Tool: %s %s\n' "$name" "$arguments" >&2
    fi

    # dispatch tools
    case "$name" in
      list_files)
        if [[ $list_files_used == true ]]; then
          result=$(tool_result 1 'Rejected: list_files can only be called once.')
        else
          list_files_used=true
          result=$(list_files)
        fi
        ;;
      read_file) result=$(read_file "$(jq -r '.filename' <<<"$arguments")") ;;
      write_file)
        if [[ $write_file_used == true ]]; then
          result=$(tool_result 1 \
            'Rejected: write_file can only be called once. Finish with a final answer.')
        else
          write_file_used=true
          result=$(write_file "$(jq -r '.filename' <<<"$arguments")" \
            "$(jq -r '.content' <<<"$arguments")")
        fi
        ;;
      *) result='{"exit_code":1,"output":"Unknown tool."}' ;;
    esac

    messages=$(jq --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
      '. + [{"role":"tool","tool_call_id":$id,"content":$result}]' <<<"$messages")
  done < <(jq -c '.choices[0].message.tool_calls[]' <<<"$answer")

  answer=$(llm)
done

# when there are no more tool calls, print the final answer
jq -er '.choices[0].message.content' <<<"$answer"
