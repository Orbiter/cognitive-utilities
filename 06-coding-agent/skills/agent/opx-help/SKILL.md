---
name: opx-help
description: >-
  Answer questions about OPX itself from its current source code. Use for
  questions about OPX behavior, tools, guardrails, configuration, prompts,
  errors, capabilities, or limitations.
---

# OPX Help

## Purpose

Answer questions about OPX from the implementation that is actually running,
not from memory or possibly outdated documentation.

## Procedure

1. Use the absolute `path` returned with this skill's tool result.
2. From the directory containing
   `.../skills/agent/opx-help/SKILL.md`, resolve `../../../opx.py`.
3. Read that `opx.py` with `read_file` before answering.
4. Inspect the relevant constants, tool schemas, handlers, and agentic loop.
5. Answer the user's question directly and name relevant functions when useful.
6. Separate behavior shown by the source from inference or runtime-dependent
   behavior.
7. Do not modify files or run Bash unless the user explicitly requests it.

If the source cannot be read, report that limitation instead of guessing.

## Completion criteria

- The current `opx.py` was read during this turn.
- The answer is supported by the inspected source.
- Runtime-dependent details and remaining uncertainty are stated explicitly.
