#!/usr/bin/env bash
# self-reading, self-writing agent that can replace and restart itself
# usage: echo "Improve your own comments." | ./opx-evo.sh [-y]

set -uo pipefail

approve_all=false
case "$#:${1:-}" in
  0:) ;;
  1:-y) approve_all=true ;;
  *) echo "Usage: <prompt> | ./opx-evo.sh [-y]" >&2; exit 1 ;;
esac

self=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")
prompt=$(cat)
restart_count=${OPX_EVO_RESTART_COUNT:-0}

llm() {
  curl -fSs "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
    -d @- <<EOF
{"model":"$OPENAI_MODEL","temperature":$OPENAI_TEMPERATURE,
"reasoning_effort":"$OPENAI_REASONING_EFFORT","stream":false,
"messages":$messages,"tools":$tools}
EOF
}

approve() {
  [[ "$approve_all" == true ]] && return 0
  printf 'Tool request: %s\nApprove? [Y/n]: ' "$1" >/dev/tty
  IFS= read -r reply </dev/tty && [[ "$reply" =~ ^([Yy]([Ee][Ss])?)?$ ]]
}

read_self() {
  approve read_self || { jq -cn '{ok:false,output:"Rejected by user."}'; return; }
  jq -Rs '{ok:true,content:.}' "$self"
}

write_self() {
  local content="$1" temporary output
  approve write_self || { jq -cn '{ok:false,output:"Rejected by user."}'; return; }
  temporary=$(mktemp "${self}.XXXXXX") || { jq -cn '{ok:false,output:"Could not create temporary file."}'; return; }
  printf '%s' "$content" >"$temporary"
  if ! output=$(bash -n "$temporary" 2>&1); then
    rm -f -- "$temporary"
    jq -cn --arg output "$output" '{ok:false,output:("Rejected invalid Bash: " + $output)}'
    return
  fi
  if chmod +x "$temporary" && mv -- "$temporary" "$self"; then
    jq -cn '{ok:true,output:"Updated opx-evo.sh."}'
  else
    rm -f -- "$temporary"
    jq -cn '{ok:false,output:"Could not replace opx-evo.sh."}'
  fi
}

messages=$(jq -n --arg prompt "$prompt" '[
  {"role":"system","content":"You are a self-modifying agent. Use exactly one tool per response. You may only read yourself, replace yourself with complete valid Bash source, and restart yourself. Read yourself before changing yourself. After a change, restart to run the new version. When the task is complete, answer briefly without a tool call."},
  {"role":"user","content":$prompt}
]')

tools='[
  {"type":"function","function":{"name":"read_self","description":"Read your complete current Bash source.","parameters":{"type":"object","properties":{},"additionalProperties":false},"strict":true}},
  {"type":"function","function":{"name":"write_self","description":"Atomically replace your Bash source after syntax validation.","parameters":{"type":"object","properties":{"content":{"type":"string","description":"Complete replacement Bash source."}},"required":["content"],"additionalProperties":false},"strict":true}},
  {"type":"function","function":{"name":"restart","description":"End this process and start the current source again with the original prompt on stdin.","parameters":{"type":"object","properties":{},"additionalProperties":false},"strict":true}}
]'

answer=$(llm)
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  name=$(jq -r '.function.name' <<<"$call")
  arguments=$(jq -r '.function.arguments' <<<"$call")
  case "$name" in
    read_self) result=$(read_self) ;;
    write_self)
      if content=$(jq -er '.content' <<<"$arguments"); then result=$(write_self "$content")
      else result='{"ok":false,"output":"Invalid write_self arguments."}'; fi
      ;;
    restart)
      if (( restart_count >= 8 )); then result='{"ok":false,"output":"Restart limit reached."}'
      elif ! approve restart; then result='{"ok":false,"output":"Rejected by user."}'
      else
        export OPX_EVO_RESTART_COUNT=$((restart_count + 1))
        restart_args=(); [[ "$approve_all" == true ]] && restart_args=(-y)
        exec "$self" "${restart_args[@]}" < <(printf '%s' "$prompt")
      fi
      ;;
    *) result='{"ok":false,"output":"Unknown tool."}' ;;
  esac
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
    '. + [$assistant,{"role":"tool","tool_call_id":$id,"content":$result}]' <<<"$messages")
  answer=$(llm)
done

jq -er '.choices[0].message.content' <<<"$answer"
