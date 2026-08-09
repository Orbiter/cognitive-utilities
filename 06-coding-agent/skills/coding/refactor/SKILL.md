# Refactor

## Purpose

Improve structure or maintainability without intentionally changing observable behavior.

## Procedure

1. State the structural problem to be improved.
2. Establish behavioral safety with existing or new tests.
3. Prefer local simplification over broad rewrites.
4. Preserve public APIs unless change is explicitly required.
5. Remove duplication, accidental complexity or unclear naming only where justified.
6. Run tests before and after the change.
7. Verify that the diff is primarily structural rather than behavioral.

## Completion criteria

- The requested outcome is implemented or the investigation is concluded.
- Relevant evidence is inspected rather than guessed.
- Any changes are checked for obvious regressions.
- Remaining uncertainty or risk is stated explicitly.
