---
name: forge-handoff
description: Writing and starting from a Asset Forge agent handoff - the file agent-handoffs/ROLE.md inside the repo that lets a fresh session continue without the old transcript, its 120-line cap, rewrite not append, and when to hand off. Use it when a task is done or you switch to unrelated work, when your context is getting long (past about 150k tokens), before the director restarts or clears a session, and at the start of any new session.
---

# Handoffs

Fresh session at every task boundary; hand off at about 200k context (memory-shared/token-and-ci-efficiency.md).
A helper past 200k asks its lead for a restart; a successor keeps the old name or a clearer one. Write
the handoff first, then start the new session from it. The user-level Stop hook blocks a turn
that changed the project without a fresh handoff; write it, never ask the director to remind you.

## Where

`agent-handoffs/<role>.md`, cap 120 lines (CI checks it), **rewritten not appended**, on your
task branch so it travels with the PR. The skeleton is `agent-handoffs/README.md`.

## What it says

State, Task (the STATUS.md item and one sentence), Branch and commit (branch, sha, worktree, PR
or "no PR yet"), Unfinished changes (what is half-done and what done looks like), Evidence so
far, Attempts (the fix-loop record: what was tried for each open bug and why it failed), Open
decisions (question ids, waiting on whom), Running jobs (PIDs, run ids), Findings for the lead (the lead curates them into
~/.claude/memory-shared/co-lead-playbook.md before any refresh), Rules learnt the hard
way (under 10 lines). A decision that exists only in a chat does not exist: once the director
answers, it goes in full under "Board and log" in the PR that acts on it.

## Starting a session from one

Read, in order: the handoff; `CLAUDE.md`; only the roadmap section you were assigned;
`docs/STATUS.md` "Assigned items" and your own row. Then check every PR the handoff names
against GitHub (`gh pr view <n>`) and that the branch tip is the sha written there. Carry on from
"Unfinished changes". With nothing assigned, say "available" and wait.

## Learnings

Proven findings for this project live in `references/learnings.md`.
