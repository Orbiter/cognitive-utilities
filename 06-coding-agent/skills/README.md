# OPX Skills

A small, portable collection of 15 skills for minimalist coding agents.

The collection is intentionally framework-agnostic. Each skill lives in its own
directory and is described by a `SKILL.md` file. A local agent can discover
skills by scanning for these files and selectively loading the relevant
instructions into the model context.

## Structure

- `coding/` – implementation, debugging, testing, refactoring and code understanding
- `git/` – history inspection
- `investigation/` – comparison workflows
- `documentation/` – README, API and architecture documentation
- `agent/` – planning, verification and OPX self-extension

Closely related workflows share one skill instead of competing for selection:

- `agent/verify-result` includes adversarial self-review;
- `coding/debug` includes defect and incident root-cause analysis; and
- `coding/understand-codebase` includes targeted codebase search.

`agent/opx-help` answers questions about OPX itself. It derives the location of
`opx.py` from its own loaded skill path and reads the current source before
answering, so the implementation remains the source of truth.

`agent/extend-skills` makes the collection self-extensible. It reads the
current catalog, creates or updates a `SKILL.md` through OPX's existing tools,
updates `skills.json`, and verifies the result through skill discovery. It may
also update its own instructions when explicitly requested.

## Minimal discovery

```bash
find skills -name SKILL.md -print
```

## Minimal loading

```bash
cat skills/coding/debug/SKILL.md
```

## Suggested agent behavior

1. Discover available skills.
2. Select only the skills relevant to the current task.
3. Load the selected `SKILL.md` files into the context.
4. Execute the task with the available tools.
5. Verify the result before returning it.

## Design principles

- Skills describe *how to work*, not implementation-specific framework behavior.
- Skills should be composable.
- Prefer verification over assumption.
- Prefer small, explicit steps over broad speculative changes.
- Keep repository-specific rules in `AGENTS.md` or equivalent; use skills for
  reusable procedures.
