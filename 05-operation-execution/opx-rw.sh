#!/usr/bin/env bash
# agentic loop with list_files, read_file, write_file, and edit_file tools
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
  output=$(cat -- "$1" 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

write_file() {
  local output exit_code
  [[ "/$1/" != */../* ]] || { tool_result 1 'Rejected: path must not contain .. components.'; return; }
  if [[ -e $1 || -L $1 ]]; then
    tool_result 1 'Rejected: file already exists.'
    return
  fi
  output=$({ set -o noclobber; printf '%s' "$2" >"$1"; } 2>&1)
  exit_code=$?
  [[ $exit_code -ne 0 ]] || output="Created $1."
  tool_result "$exit_code" "$output"
}

edit_file() {
  local output= exit_code content old new prefix start end previous offset=0
  local -a ends=() replacements=()
  [[ "/$1/" != */../* ]] || { tool_result 1 'Rejected: path must not contain .. components.'; return; }
  jq -e 'type == "array" and length > 0 and all(.[];
    keys == ["newText", "oldText"] and (.oldText | type == "string" and length > 0)
    and (.newText | type == "string"))' >/dev/null 2>&1 <<<"$2" ||
    { tool_result 1 'Rejected: invalid edits or empty oldText.'; return; }
  # A sentinel preserves trailing newlines in command substitutions.
  content=$(cat -- "$1" 2>&1 && printf '.') || { tool_result 1 "$content"; return; }
  content=${content%.}
  while IFS= read -r -d '' old && IFS= read -r -d '' new; do
    prefix=${content%%"$old"*}
    start=${#prefix}
    [[ $prefix != "$content" && ${content:start+1} != *"$old"* ]] ||
      { tool_result 1 'Rejected: every oldText must occur exactly once.'; return; }
    end=$((start + ${#old}))
    for previous in "${!ends[@]}"; do
      (( start >= ends[previous] || end <= previous )) ||
        { tool_result 1 'Rejected: edits overlap; nothing was changed.'; return; }
    done
    ends[start]=$end replacements[start]=$new
  done < <(jq -j '.[] | .oldText, "\u0000", .newText, "\u0000"' <<<"$2")
  # Indexed arrays visit positions in ascending order.
  for start in "${!ends[@]}"; do
    output+=${content:offset:start-offset}${replacements[start]}
    offset=${ends[start]}
  done
  output=$({ printf '%s' "$output${content:offset}" >"$1"; } 2>&1)
  exit_code=$?
  [[ $exit_code -ne 0 ]] || output="Updated $1."
  tool_result "$exit_code" "$output"
}

system_prompt='You are a coding assistant working in the current directory.

Available tools:
- Use list_files to inspect the current directory.
- Use read_file to read file contents.
- Use write_file to create new files.
- Use edit_file to replace exact text in an existing file.'

messages=$(jq -n --arg system_prompt "$system_prompt" --arg prompt "$(cat)" '[
  {"role":"system","content":$system_prompt},
  {"role":"user","content":$prompt}
]')

tools='[
  {
    "type": "function",
    "function": {
      "name": "list_files",
      "description": "List the current directory with ls -la.",
      "parameters": {
        "type": "object", "properties": {}, "additionalProperties": false
      },
      "strict": true
    }
  },
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read a complete file from the current directory.",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {
            "type": "string", "description": "A file path without .. components."
          }
        },
        "required": ["filename"], "additionalProperties": false
      },
      "strict": true
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_file",
      "description": "Create a new file in the current directory. The filename must not contain '..'.",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {
            "type": "string", "description": "A new file name without '..'. It must not already exist."
          },
          "content": {"type": "string"}
        },
        "required": ["filename", "content"], "additionalProperties": false
      },
      "strict": true
    }
  },
  {
    "type": "function",
    "function": {
      "name": "edit_file",
      "description": "Replace unique, non-empty oldText matches in an existing file. Reject missing, repeated, or overlapping matches without changing the file.",
      "parameters": {
        "type": "object",
        "properties": {
          "filename": {"type": "string", "description": "An existing file path without .. components."},
          "edits": {
            "type": "array", "minItems": 1,
            "items": {
              "type": "object",
              "properties": {"oldText": {"type": "string"}, "newText": {"type": "string"}},
              "required": ["oldText", "newText"], "additionalProperties": false
            }
          }
        },
        "required": ["filename", "edits"], "additionalProperties": false
      },
      "strict": true
    }
  }
]'

# start the agentic loop
answer=$(llm)
while jq -e '.choices[0].message.tool_calls | length > 0' >/dev/null <<<"$answer"; do
  assistant=$(jq '.choices[0].message' <<<"$answer")
  messages=$(jq --argjson assistant "$assistant" '. + [$assistant]' <<<"$messages")

  # process tool calls
  while IFS= read -r call; do
    name=$(jq -r '.function.name' <<<"$call")
    arguments=$(jq -r '.function.arguments' <<<"$call")
    if [[ $name == write_file || $name == edit_file ]]; then
      printf 'Tool: %s %s\n' "$name" "$(jq -c '{filename}' <<<"$arguments")" >&2
    else
      printf 'Tool: %s %s\n' "$name" "$arguments" >&2
    fi

    # dispatch tools
    case "$name" in
      list_files) result=$(list_files) ;;
      read_file) result=$(read_file "$(jq -r '.filename' <<<"$arguments")") ;;
      edit_file)
        result=$(edit_file "$(jq -r '.filename' <<<"$arguments")" \
          "$(jq -c '.edits' <<<"$arguments")")
        ;;
      write_file)
        result=$(write_file "$(jq -r '.filename' <<<"$arguments")" \
          "$(jq -r '.content' <<<"$arguments")")
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
