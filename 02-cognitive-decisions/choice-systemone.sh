#!/usr/bin/env bash
# simple filter example: text to bug|feature|question|other
# usage: echo 'The application crashes during startup.' | ./choice-systemone.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$SYSTEMONE_BASE_URL/v1/systemone" \
  -H "Authorization: Bearer $SYSTEMONE_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.answers.category'
{
  "model": "$SYSTEMONE_MODEL",
  "state": $input_json,
  "questions": {
    "category": {
      "type": "choice",
      "instructions": "Classify the input.",
      "criteria": {
        "bug": "A software defect, failure or unexpected behavior.",
        "feature": "A request for new functionality or an improvement.",
        "question": "A request for information or an explanation.",
        "other": "None of the above."
      }
    }
  }
}
EOF
