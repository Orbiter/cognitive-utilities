#!/usr/bin/env bash

# check if this script was used correctly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: you must execute this script in your current shell:" >&2
    echo "  source configure.sh" >&2
    echo "or:" >&2
    echo "  . ./configure.sh" >&2
    exit 1
fi

# define environment for demo: small local model, deterministic, no thinking
export OPENAI_BASE_URL="http://localhost:11434"
export OPENAI_API_KEY="_"
export OPENAI_MODEL="gemma4:12b-it-qat"
export OPENAI_TEMPERATURE="0.0"
export OPENAI_REASONING_EFFORT="none"

# make sure environment is supported by inference engine
echo "Pulling model $OPENAI_MODEL for ollama" >&2
ollama pull $OPENAI_MODEL
