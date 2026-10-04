#!/usr/bin/env bash
# yes/no example: text to probability of a refund request (0..1)
# usage: echo 'Please refund my payment.' | ./detect-refund-systemone.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$SYSTEMONE_BASE_URL/v1/systemone" \
  -H "Authorization: Bearer $SYSTEMONE_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.answers.refund.noul'
{
  "model": "$SYSTEMONE_MODEL",
  "state": $input_json,
  "questions": {
    "refund": {
      "type": "noul",
      "instructions": "Does the customer ask to receive money back?",
      "criteria": {
        "false": "The message does not ask for money to be returned.",
        "true": "The message asks for a full or partial repayment."
      }
    }
  }
}
EOF
