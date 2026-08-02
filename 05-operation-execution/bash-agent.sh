#!/usr/bin/env bash
# execute approved bash commands to answer a request
# usage: echo "Inspect /var/log and report recent errors. Make a full audit." | ./bash-agent.sh

set -uo pipefail

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

# Turn the complete input stream into the initial conversation.
messages=$(jq -n --arg prompt "$(cat)" '[
  {"role":"system","content":"You are a Linux system operator running in the current working directory. Use bash to inspect the system until you can answer. Submit only one command per tool call and give a short final answer."},
  {"role":"user","content":$prompt}
]')

# Define bash as the agent's only tool and require one command argument.
tools='[{"type":"function","function":{
  "name":"bash","description":"Run one bash command and return its output.",
  "parameters":{"type":"object","properties":{
    "command":{"type":"string","description":"One bash command without pipes, redirections, command separators, or newlines."}
  },"required":["command"],"additionalProperties":false},"strict":true
}}]'

# Start the conversation and let the model decide whether it needs bash.
answer=$(llm)

# Continue the agentic loop while the model requests a tool call.
while call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); do
  # Decode the JSON arguments generated for the bash tool.
  command=$(jq -er '.function.arguments | fromjson | .command' <<<"$call")

  # Reject shell composition so every tool call remains one inspectable command.
  case "$command" in
    *'|'*|*';'*|*'&'*|*'>'*|*'<'*|*$'\n'*|*$'\r'*)
      exit_code=1
      output="Rejected: use one command without pipes, redirections, separators, or newlines."
      ;;
    *)
      # Keep execution under human control even though the model chose the command.
      printf 'Tool request: %s\nApprove? [Y/n]: ' "$command" >/dev/tty
      if IFS= read -r reply </dev/tty && [[ "$reply" =~ ^([Yy]([Ee][Ss])?)?$ ]]; then
        output=$(bash -c "$command" 2>&1)
        exit_code=$?
      else
        exit_code=1
        output="Rejected by user."
      fi
      ;;
  esac

  # Return both output and exit status so the model can interpret failures correctly.
  result=$(jq -cn --argjson exit_code "$exit_code" --arg output "$output" \
    '{exit_code:$exit_code,output:$output}')
  # Preserve the assistant tool call and append its matching result to the conversation.
  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg result "$result" \
    '. + [$assistant,{"role":"tool","tool_call_id":$id,"content":$result}]' <<<"$messages")
  answer=$(llm)
done

# Once no tool is requested, print the model's final answer.
jq -er '.choices[0].message.content' <<<"$answer"
