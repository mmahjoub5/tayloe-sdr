---
name: update-claude-md
description: Add or update a topic section in the project CLAUDE.md (repo root, /Users/aminmahjoub/Documents/pcb/radio/CLAUDE.md) after a big commit. Use right after committing something large in this repo — a new package or module (e.g. radiolib/ft8), a new subsystem, renamed or moved directories, new entry points or test commands, new data files — or when asked to "document this in CLAUDE.md". Skip it for small fixes, tweaks and refactors that don't change layout or usage.
---

# Update CLAUDE.md after a big commit

## 1. Decide whether the commit is big enough
Look at what the commit changed:

    git show --stat HEAD
    git log -1 --format=%B

Write a section when the commit adds or changes any of these:
- a new package, module or subsystem (code, CAD, KiCad, GNU Radio flowgraphs)
- moved or renamed directories
- how to run, test or build something
- new data or matrix files, or a non-obvious constraint (sample rates, filename quirks)

Otherwise stop and say that nothing needed documenting.

## 2. Read before you write
- Read the whole of `CLAUDE.md`. If the topic already has a section, update that section
  instead of adding another one.
- Read the files the commit added (their module docstrings, `__main__`, `pyproject.toml`)
  so every path, name and command you write is one you checked. Don't write any from memory.

## 3. Write the section
Use the format of the existing sections:
- `## <topic> (\`path/\`)` heading, then one line on what it is.
- One bullet per file or part: what it holds and the key names (classes, functions, constants).
- Commands in an indented block, with the directory they run from.
- Quirks someone would trip over (misspellings that are real filenames, fixed rates,
  files that must change together).

Leave out:
- Transient state ("uncommitted", "WIP", "next I'll…"), dates, and commit hashes.
- Anything a skill already covers in depth (e.g. the FT8 protocol in `ft8-spec`).
  Point to the skill by name instead.
- History and changelog material; git keeps that.

Keep each section short: a reader should get the layout and commands at a glance.

## 4. Finish
- Show the user the diff of `CLAUDE.md`.
- Don't commit it yourself. Offer to commit it, or to amend it into the big commit if
  that commit hasn't been pushed.
