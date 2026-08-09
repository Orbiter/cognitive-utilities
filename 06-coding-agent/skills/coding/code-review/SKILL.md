# Code Review

## Purpose

Review a change for correctness, regressions, maintainability, security and missing tests.

## Procedure

1. Understand the stated intent of the change.
2. Inspect the diff and surrounding code, not the diff in isolation.
3. Prioritize correctness bugs and behavioral regressions over style.
4. Check error handling, boundaries, state changes, concurrency and security where relevant.
5. Look for missing or misleading tests.
6. Distinguish blocking issues from optional improvements.
7. Provide concrete file/line-oriented findings and explain the failure mode.

## Completion criteria

- The requested outcome is implemented or the investigation is concluded.
- Relevant evidence is inspected rather than guessed.
- Any changes are checked for obvious regressions.
- Remaining uncertainty or risk is stated explicitly.
