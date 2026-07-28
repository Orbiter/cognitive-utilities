#!/usr/bin/env bash
# autonomous fractal research with visible experiments
# usage: echo "Find a smaller copy of the initial image." | ./mandelbrot.sh
set -euo pipefail

# Render one observation. The scale is the width of the complex-plane window.
render() {
  awk -v cx="$1" -v cy="$2" -v scale="$3" 'BEGIN {
    cols=60; rows=24; max=800
    shades=" .,:;irsXA253hMHGS#9B&@"
    printf "observation: center=(%.7f, %.7f), scale=%.7g\n",cx,cy,scale
    for (py=0; py<rows; py++) {
      y=cy+((rows-1)/2-py)*scale*0.75/rows
      for (px=0; px<cols; px++) {
        x=cx+(px-cols/2)*scale/cols
        zr=0; zi=0
        for (n=0; n<max && zr*zr+zi*zi<=4; n++) {
          next_zr=zr*zr-zi*zi+x
          zi=2*zr*zi+y; zr=next_zr
        }
        inside[py,px]=(n==max)
        width[py]+=inside[py,px]; total+=inside[py,px]
        shade=n==max ? length(shades) : int(sqrt(n/max)*(length(shades)-1))+1
        printf "%s",substr(shades,shade,1)
      }
      print ""
    }
    for (py=0; py<rows; py++)
      for (px=0; px<cols; px++)
        different+=(inside[py,px] != inside[rows-1-py,px])
    printf "measurements: fill_ratio=%.3f, horizontal_symmetry=%.3f\n",
      total/(cols*rows),1-different/(cols*rows)
    printf "silhouette_profile: ["
    for (py=0; py<rows; py++)
      printf "%d%s",width[py],(py==rows-1 ? "]\n" : ",")
    split("0,0,0,4,4,9,17,19,22,26,31,31,31,31,26,22,19,17,9,4,4,0,0,0",reference,",")
    for (py=0; py<rows; py++)
      squared+=(width[py]-reference[py+1])^2
    printf "silhouette_similarity: %.3f\n",1-sqrt(squared/rows)/cols
  }'
}

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

reference=$(render -0.5 0 3)
printf '# Reference image\n%s\n' "$reference"

messages=$(jq -n --arg prompt "$(cat)" --arg reference "$reference" '[
  {"role":"system","content":("You are an autonomous fractal researcher. The reference image and measurements are:\n"+$reference+"\nA prepared specimen is centered at (-1.99637834, 0). Discover whether increasing its magnification reveals a smaller copy of the reference body, bulb, and antenna. The magnify tool advances the microscope by one small step and returns the next observation. Conduct exactly one experiment per response. If its assessment says the evidence is insufficient, your entire next response must be another magnify call. Return text only when visual and quantitative evidence support the thesis. Report the complete experiment sequence under the headings Thesis, Experiments, Observations, and Conclusion.")},
  {"role":"user","content":$prompt}
]')
tools='[{"type":"function","function":{
  "name":"magnify","description":"Advance the microscope by one small magnification step and render the next ASCII observation.",
  "parameters":{"type":"object","properties":{},"additionalProperties":false},"strict":true
}}]'

answer=$(llm)
calls=0
evidence_sufficient=false
reviews=0

while true; do
  if ! call=$(jq -e '.choices[0].message.tool_calls[0]' <<<"$answer"); then
    if [[ "$evidence_sufficient" == true ]]; then
      break
    fi
    ((reviews += 1))
    ((reviews <= 5)) || { echo "Error: conclusion rejected too often" >&2; exit 1; }
    messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
      '. + [$assistant, {"role":"user","content":"Peer review rejected the conclusion: the measured fill ratio and silhouette are not yet close to the reference. Continue with another render experiment."}]' <<<"$messages")
    answer=$(llm)
    continue
  fi

  ((calls += 1))
  ((calls <= 20)) || { echo "Error: tool call limit reached" >&2; exit 1; }
  scale=$(awk -v step="$calls" 'BEGIN {print 0.0001/(1.35^(step-1))}')
  observation=$(render -1.99637834 0 "$scale")
  fill_ratio=$(sed -n 's/^measurements: fill_ratio=\([^,]*\).*/\1/p' <<<"$observation")
  similarity=$(sed -n 's/^silhouette_similarity: //p' <<<"$observation")
  if awk -v fill="$fill_ratio" -v similarity="$similarity" \
    'BEGIN {difference=fill-0.226; if (difference<0) difference=-difference; exit !(difference<=0.06 && similarity>=0.86)}'
  then
    evidence_sufficient=true
    observation+=$'\nassessment: the evidence supports a match; report the conclusion.'
  else
    evidence_sufficient=false
    observation+=$'\nassessment: evidence is insufficient; conduct another experiment.'
  fi
  printf '\n# Experiment %d\n%s\n' "$calls" "$observation"

  messages=$(jq --argjson assistant "$(jq '.choices[0].message' <<<"$answer")" \
    --arg id "$(jq -r '.id' <<<"$call")" --arg observation "$observation" \
    '. + [$assistant, {"role":"tool","tool_call_id":$id,"name":"magnify","content":$observation}]' <<<"$messages")
  answer=$(llm)
done

jq -er '.choices[0].message.content' <<<"$answer"
