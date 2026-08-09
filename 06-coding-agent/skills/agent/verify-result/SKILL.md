# Verify Result

## Purpose

Check that completed work satisfies the request and critically review it before
returning it.

## Procedure

1. Re-read the requested outcome and constraints.
2. Inspect the final diff or generated artifact.
3. Look for assumptions that were never validated.
4. Check whether the solution is broader or more complex than necessary.
5. Search for obvious bugs, missing error paths and inconsistent naming.
6. Run targeted tests, commands or validation steps.
7. Check important negative cases and compatibility concerns.
8. Confirm that tests exercise the changed behavior.
9. Confirm no temporary files, debug output or accidental edits remain.
10. Fix discovered problems, then report what was and was not verified.

## Completion criteria

- The final result matches the request and its constraints.
- Relevant checks pass, or failures are reported explicitly.
- Obvious regressions, unnecessary complexity and accidental edits are absent.
- Remaining uncertainty or risk is stated explicitly.
