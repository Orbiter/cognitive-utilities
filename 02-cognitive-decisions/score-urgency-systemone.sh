#!/usr/bin/env bash
# scoring example: support ticket to urgency score (0..2)
# usage: 
# echo 'The button should be green' | ./score-urgency-systemone.sh
# echo 'Printing does not work' | ./score-urgency-systemone.sh
# echo 'Production is down' | ./score-urgency-systemone.sh

set -euo pipefail
input_json=$(jq -Rn --arg value "$(cat)" '$value')
curl -fSs "$SYSTEMONE_BASE_URL/v1/systemone" \
  -H "Authorization: Bearer $SYSTEMONE_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF | jq -er '.answers.urgency.score'
{
  "model": "$SYSTEMONE_MODEL",
  "state": $input_json,
  "questions": {
    "urgency": {
      "type": "score",
      "instructions": "Rate the urgency of this input based on impact.",
      "criteria": [
        "Low: a general question, suggestion or cosmetic issue.",
        "Medium: functionality is impaired or the impact is limited.",
        "High: a critical failure and needs immediate attention."
      ]
    }
  }
}
EOF
