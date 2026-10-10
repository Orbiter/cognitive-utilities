#!/usr/bin/env bash
# agentic loop with list_files, search_files, read_file, write_file, and edit_file tools
# search_files requires ripgrep (rg).
# usage: echo "Read notes.txt and write a summary to report.md." | ./opx-rw.sh [--systemprompt FILE]
#
# examples:
# echo "List the files in this directory and explain what this project contains." | ./opx-rw.sh
# echo "Read README.md and summarize the workshop in five bullet points." | ./opx-rw.sh
# echo "Find TODO comments in shell scripts throughout this directory tree." | ./opx-rw.sh
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
  local output exit_code path arguments=${1:-'{}'}
  local -a options=(-la)
  jq -e 'type == "object" and
    (.path == null or (.path | type == "string" and length > 0 and (contains("\u0000") | not))) and
    (.recursive == null or (.recursive | type == "boolean"))' >/dev/null 2>&1 <<<"$arguments" ||
    { tool_result 1 'Rejected: invalid listing arguments.'; return; }
  IFS= read -r -d '' path < <(jq -j '(.path // "."), "\u0000"' <<<"$arguments")
  [[ $path != /* && "/$path/" != */../* ]] ||
    { tool_result 1 'Rejected: path must be relative and must not contain .. components.'; return; }
  [[ $(jq -r '.recursive // false' <<<"$arguments") == false ]] || options+=(-R)
  output=$(ls "${options[@]}" -- "./$path" 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

read_file() {
  local output exit_code
  output=$(cat -- "$1" 2>&1)
  exit_code=$?
  tool_result "$exit_code" "$output"
}

search_files() {
  local output exit_code pattern path glob context_lines max_results
  local -a options=(--no-config --json --sort path)
  jq -e 'type == "object" and
    (.pattern | type == "string" and (contains("\u0000") | not)) and
    (.path == null or (.path | type == "string" and length > 0 and (contains("\u0000") | not))) and
    (.glob == null or (.glob | type == "string" and (contains("\u0000") | not))) and
    (.fixed_strings == null or (.fixed_strings | type == "boolean")) and
    (.ignore_case == null or (.ignore_case | type == "boolean")) and
    (.context_lines == null or (.context_lines | type == "number" and . >= 0 and . == floor)) and
    (.max_results == null or (.max_results | type == "number" and . > 0 and . == floor))' \
    >/dev/null 2>&1 <<<"$1" || { tool_result 2 'Rejected: invalid search arguments.'; return; }
  # NUL-delimited reads preserve whitespace, including trailing newlines.
  IFS= read -r -d '' pattern < <(jq -j '.pattern, "\u0000"' <<<"$1")
  IFS= read -r -d '' path < <(jq -j '(.path // "."), "\u0000"' <<<"$1")
  IFS= read -r -d '' glob < <(jq -j '(.glob // ""), "\u0000"' <<<"$1")
  [[ $path != /* && "/$path/" != */../* ]] ||
    { tool_result 2 'Rejected: path must be relative and must not contain .. components.'; return; }
  command -v rg >/dev/null 2>&1 || { tool_result 127 'search_files requires ripgrep (rg).'; return; }
  context_lines=$(jq -r '.context_lines // 0' <<<"$1")
  max_results=$(jq -r '.max_results // 100' <<<"$1")
  [[ $(jq -r '.fixed_strings // false' <<<"$1") == false ]] || options+=(--fixed-strings)
  [[ $(jq -r '.ignore_case // false' <<<"$1") == false ]] || options+=(--ignore-case)
  [[ -z $glob ]] || options+=(--glob "$glob")
  # Drain the stream after the global match limit to preserve ripgrep errors.
  # Keep stderr outside the filter so diagnostics are never truncated.
  output=$({
    rg "${options[@]}" --context "$context_lines" --regexp "$pattern" -- "./$path" |
      jq -nr --argjson limit "$max_results" '
        foreach inputs as $event (0;
          if $event.type == "match" then . + 1 else . end;
          if $event.type == "match" and . == $limit + 1 then
            "[Truncated: more than \($limit) matching lines. Narrow the search or increase max_results.]"
          elif ($event.type == "match" or $event.type == "context") and . <= $limit then
            "\($event.data.path.text // ($event.data.path.bytes | @base64d)):\($event.data.line_number):\($event.data.lines.text // ($event.data.lines.bytes | @base64d) | rtrimstr("\n"))"
          else empty end)'
  } 2>&1)
  exit_code=$?
  if [[ $exit_code -eq 1 ]]; then
    exit_code=0 output='No matches found.'
  fi
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

system_prompt='You are a file editor assistant working in the current directory.

Available tools:
- Use list_files with path to inspect a subdirectory, or recursive true to list its entire tree. Paths are relative to the current directory.
- Use search_files to search file contents recursively with ripgrep. Results include paths and line numbers; hidden, ignored, and binary files are skipped by default.
- Use read_file to read files, including files in subdirectories.
- Use write_file to create new files in existing directories, including subdirectories.
- Use edit_file to replace exact text in an existing file, including files in subdirectories.'

usage() { printf 'Usage: %s [--systemprompt FILE] < prompt\n' "$0"; }
system_message=$(jq -cn --arg content "$system_prompt" '{role:"system",content:$content}')
while (( $# )); do
  case "$1" in
    --systemprompt)
      [[ $# -ge 2 && $2 != -* ]] || { usage >&2; exit 2; }
      system_message=$(jq -c --rawfile extra "$2" '.content += "\n\n" + $extra' <<<"$system_message") || exit 1
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

messages=$(jq -Rs --argjson system_message "$system_message" '[
  $system_message, {role:"user",content:.}
]')

tools=$(jq -cn '
  def object_schema($properties):
    {type:"object", properties:$properties, required:($properties | keys_unsorted), additionalProperties:false};
  def tool($name; $description; $properties):
    {type:"function", function:{name:$name, description:$description,
      parameters:object_schema($properties), strict:true}};
  [
    tool("list_files"; "List a directory with ls -la; optionally include its complete subtree with ls -laR.";
      {
        path: {type:["string", "null"], description:"Relative directory path without .. components. Null defaults to the current directory."},
        recursive: {type:["boolean", "null"], description:"List all descendant directories too. Null defaults to false."}
      }),
    tool("search_files";
      "Search file contents recursively with ripgrep. Returns path:line:text for matching and context lines. The global limit counts matching lines, not context lines; truncation is reported. No matches is a successful result.";
      {
        pattern: {type:"string", description:"Ripgrep regular expression, or literal text when fixed_strings is true."},
        path: {type:["string", "null"], description:"Relative file or directory path without .. components. Null searches the current directory tree."},
        fixed_strings: {type:["boolean", "null"], description:"Treat pattern as literal text. Null defaults to false."},
        ignore_case: {type:["boolean", "null"], description:"Ignore capitalization. Null defaults to false."},
        glob: {type:["string", "null"], description:"Optional file glob such as *.sh or !vendor/**. Null applies no extra filter."},
        context_lines: {type:["integer", "null"], minimum:0, description:"Lines before and after each match. Null defaults to 0."},
        max_results: {type:["integer", "null"], minimum:1, description:"Maximum matching lines returned across all files. Null defaults to 100."}
      }),
    tool("read_file"; "Read a complete file, including files in subdirectories.";
      {filename: {type:"string", description:"A file path such as src/notes.txt, without .. components."}}),
    tool("write_file"; "Create a new file in an existing directory, including subdirectories. The filename must not contain '\''..'\''.";
      {
        filename: {type:"string", description:"A new file path such as src/notes.txt, without '\''..'\''. Its parent directory must exist; the file must not."},
        content: {type:"string"}
      }),
    tool("edit_file";
      "Replace unique, non-empty oldText matches in an existing file. Reject missing, repeated, or overlapping matches without changing the file.";
      {
        filename: {type:"string", description:"An existing file path such as src/notes.txt, without .. components."},
        edits: {type:"array", minItems:1, items:object_schema({oldText:{type:"string"}, newText:{type:"string"}})}
      })
  ]')

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
      list_files) result=$(list_files "$arguments") ;;
      search_files) result=$(search_files "$arguments") ;;
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
