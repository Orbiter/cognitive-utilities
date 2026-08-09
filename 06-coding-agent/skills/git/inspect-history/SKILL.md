# Inspect Git History

## Purpose

Use repository history to understand why code exists, when behavior changed or who introduced it.

## Procedure

1. Start from the relevant file, symbol or line.
2. Use `git log`, `git blame` and path-limited history to find candidate changes.
3. Inspect the full commit diff and message for context.
4. Compare behavior before and after the relevant change.
5. Follow renames when necessary.
6. Summarize historical evidence separately from inference.

## Completion criteria

- The requested outcome is implemented or the investigation is concluded.
- Relevant evidence is inspected rather than guessed.
- Any changes are checked for obvious regressions.
- Remaining uncertainty or risk is stated explicitly.
