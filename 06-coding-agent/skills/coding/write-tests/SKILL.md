# Write Tests

## Purpose

Create focused tests that protect important behavior and catch plausible regressions.

## Procedure

1. Identify observable behavior and invariants.
2. Reuse the project's existing test framework and conventions.
3. Cover the happy path, relevant boundaries and at least one likely failure mode.
4. Avoid tests that merely mirror implementation details.
5. Prefer deterministic tests with minimal setup.
6. Run the new tests and confirm they fail for the intended defect when applicable.
7. Keep fixtures and mocks as small as practical.

## Completion criteria

- The requested outcome is implemented or the investigation is concluded.
- Relevant evidence is inspected rather than guessed.
- Any changes are checked for obvious regressions.
- Remaining uncertainty or risk is stated explicitly.
