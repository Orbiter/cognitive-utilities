---
name: extend-skills
description: >-
  Add or update skills in OPX's own skill collection. Use when the user asks
  OPX to create, extend, reorganize, or maintain its skills or skill catalog.
---

# Extend Skills

## Purpose

Extend OPX through its existing file and Bash tools. Treat the loaded skill
collection and `skills.json` as editable parts of OPX itself.

## Procedure

1. Use the absolute `path` returned with this skill's tool result.
2. From this `SKILL.md` directory, resolve `../..` as the skills directory and
   `../../skills.json` as the catalog.
3. Read `skills.json` and any related skills before changing them.
4. Choose a unique lowercase, hyphenated path below an appropriate category.
5. Keep the new skill concise and give it YAML `name` and `description` fields
   that clearly state what it does and when it should be loaded.
6. For a new skill, request approval for one `mkdir -p` Bash command, then use
   `write_file` to create its `SKILL.md`.
7. Use `replace_in_file` to add or update its `name`, `path`, `file`, and
   `purpose` entry in `skills.json` while preserving valid JSON.
8. For an existing skill, read it first and make the smallest exact replacement.
9. Call `list_skills`, then `read_skill` for the changed skill to verify that
   discovery and loading both work.
10. Report created and changed paths plus any approval or validation failure.

This skill may update its own `SKILL.md` and catalog entry when the user asks it
to improve its skill-extension procedure. Reload it afterward to verify the new
instructions. Do not delete a skill unless the user explicitly requests it.

## Completion criteria

- The skill file and catalog entry agree.
- Skill names and paths are unique.
- `list_skills` succeeds and `read_skill` loads the changed skill.
- No unrelated skill or source file was changed.
