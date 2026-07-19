#!/usr/bin/env bash

# check if this script was used correctly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: you must execute this script in your current shell:" >&2
    echo "  source configure.sh" >&2
    echo "or:" >&2
    echo "  . ./configure.sh" >&2
    exit 1
fi

export OPENAI_BASE_URL="http://localhost:11434"
export OPENAI_API_KEY="_"
export OPENAI_MODEL="qwen3.5:4b-q4_K_M"
