# Understand Codebase

## Purpose

Locate relevant code efficiently and build a reliable mental model of an unfamiliar
repository before making changes.

## Procedure

1. Inspect top-level files, build manifests and repository documentation.
2. Search exact symbols, error strings, config keys and endpoint names first.
3. Expand through imports, callers, references and tests rather than reading every
   file sequentially.
4. Distinguish definitions, references and generated copies.
5. Identify entry points, major modules and runtime boundaries.
6. Trace one representative request or execution path end to end.
7. Inspect tests to infer intended behavior.
8. Note configuration, generated code and external dependencies.
9. Record the minimal set of files that controls the relevant behavior.
10. Summarize components, responsibilities and data flow, marking uncertain
    assumptions explicitly.

## Completion criteria

- Relevant entry points, callers, tests and configuration have been located.
- The controlling files and execution path are identified.
- The resulting explanation is based on inspected evidence.
- Remaining uncertainty is stated explicitly before editing.
