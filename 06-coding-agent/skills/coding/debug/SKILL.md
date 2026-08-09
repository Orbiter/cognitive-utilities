# Debug

## Purpose

Identify the root cause of a defect or incident, then apply the smallest justified
fix when a change is requested.

## Procedure

1. Reproduce or precisely characterize the failure.
2. Establish the timeline when investigating an incident.
3. Inspect errors, logs, failing input, recent changes and the relevant code path.
4. Separate the trigger, contributing conditions and underlying cause.
5. Form concrete hypotheses and test the cheapest discriminating one first.
6. Trace data and control flow to the first divergence from intended behavior.
7. Avoid vague explanations such as human error without a technical cause.
8. If a fix was requested, fix the cause rather than only the visible symptom.
9. Re-run the failing case and nearby regression cases.
10. Summarize evidence, cause, fix or remediation, confidence and open questions.

## Completion criteria

- The explanation identifies the first incorrect state and its supporting evidence.
- A requested fix addresses the cause and passes the relevant checks.
- Preventive actions are distinguished from immediate remediation when relevant.
- Confidence and unresolved questions are stated explicitly.
