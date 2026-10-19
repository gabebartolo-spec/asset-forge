# Agent handoffs

One file per role (`lead.md`, `merge.md`, `art.md`, …), cap 120 lines, rewritten not appended,
on the role's task branch so it travels with the PR. The `forge-handoff` skill says what goes
in it. The user-level Stop hook blocks a turn that changed the project without a fresh handoff.

```
# <Role> handoff, <date> <time>
## State: working | running a check | awaiting director | blocked | available
## Task
## Branch and commit
## Unfinished changes
## Evidence so far
## Attempts (fix-loop record)
## Open decisions
## Running jobs
## Findings for the lead
(what helped or caught a defect this task, with evidence, or "none"; the lead records the worthwhile
ones in ~/.claude/memory-shared/co-lead-playbook.md. Leads write "playbook: updated" or "nothing new")
## Rules learnt the hard way (under 10 lines)
```
