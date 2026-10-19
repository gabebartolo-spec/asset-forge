---
name: forge-pr
description: Opening, syncing and handing over a pull request the Asset Forge way - worktree and branch, the PR body sections and [MERGE NOTE], director gates, who merges, the Board and log section. Extends the general github-hygiene skill (~/.claude/skills) with this repo's template, board rules and roles. Use it whenever you are about to open a PR, update one after main moved, or tell another agent about a PR or CI result.
---

# A PR the Asset Forge way

The general rules are the `github-hygiene` skill; read it first. This file holds only what
Asset Forge adds.

## Before you start

Work only on what `docs/STATUS.md` "Assigned items" lists. Branch from current main in your own
worktree; more than four live is a violation (`bash tools/lint/worktrees.sh`):

```bash
git fetch -q origin
git worktree add -b claude/<topic> ../asset-forge-wt/<topic> origin/main
```

One PR per branch. Commit subjects take a prefix (`gen:` `clean:` `rig:` `anim:` `sprite:` `ui:` `tools:` `docs:`
`tests:` `ci:`), stay under 72 characters, present tense, and say what the director gets when
the change is visible.

## The PR body

`.github/PULL_REQUEST_TEMPLATE.md` is the shape; keep every heading. A body with a section
missing, or no "Not exercised" line, is not ready.

## STATUS.md and DECISIONS.md: never in your PR

Only the lead edits `docs/STATUS.md` and `docs/DECISIONS.md`. Put your row change and any
decision, in full as `D-TBD-<slug>`, under "## Board and log" in the PR body; the merge role
records them in a board PR after the merge.

## After opening

- Only the lead merges. Green + eligible = merge, for the exact head
  commit, after any required review and director gate. Never enable auto-merge.
- Sync your own branch when main moves under it. Remove your worktree when the PR merges.
- Hand over at task boundaries: `agent-handoffs/<role>.md` (see forge-handoff).

## Learnings

Proven findings for this project live in `references/learnings.md`. Read it before using this
skill; add to it only what proved effective, with evidence. General lessons go to
`github-hygiene/references/learnings.md`.
