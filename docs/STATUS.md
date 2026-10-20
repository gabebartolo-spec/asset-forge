# Status board

Cap: 150 lines. Edited only by the lead, in a board PR after each merge, from the merged PR's
"Board and log" section. History rolls to `docs/archive/status_<month>.md`.

## Phase
Current phase: **2 — Generate and Clean** (finishing), with Phase 3 Skeleton done, and Phase 4
Animation, Phase 5 Sprites mode A and Phase 6 Library and batch running in parallel (D-022,
D-025). Phase 1 done 2026-10-20 (D-019).

## Agents

| Agent | State | Item | Branch / PR | Since |
|-------|-------|------|-------------|-------|
| Lead | working | board; critics; merges | this PR | 2026-10-20 |
| clean-critic-r4 | running a check | item 5 (round-4 realism/fidelity) | #9 | 2026-10-20 |
| sprites-b4 | working | item 7 (finish: spurs, real runs, PR body) | #11 | 2026-10-20 |
| anim-b1 | working | item 10 (Animation first slice) | claude/animation | 2026-10-20 |
| library-b1 | working | item 11 (Library and batch) | claude/library (no PR yet) | 2026-10-20 |

States: working · running a check · awaiting director · blocked · available.

## Assigned items (in order; an item starts only when it is listed here)

### Phase 0 (assigned by the director, 2026-10-19: "set it up so i can begin development")
1. DONE 2026-10-20. Gate proved with throwaway PRs (`docs/audits/kickoff_gate.md`).
2. DONE 2026-10-20 (Hunyuan dropped, D-010). Licence rows for every candidate.

### Phase 1 — Generator bake-off
3. DONE 2026-10-20 (D-019: Hi3DGen then TripoSG; PR #6).

### Phase 2 — Generate and Clean (assigned 2026-10-20: "Yes, split it in two", "spawn 1 more")
4. DONE 2026-10-20. App shell + Step 1 Generate + generator menu (PR #8); text-only input and
   "Expand my idea" in the page (PR #14).
5. Step 2 Clean + gates (PR #9). Round 4: colour is a measured region gate (method change after
   three tuning rounds). Fresh critic running. Then the Step 2 page and the Step 2 -> Step 3
   hand-over (item 12).
6. DONE 2026-10-20. Export gate + headless Godot import check (PR #7).
12. Step 2 page + hand-over to Step 3, starts the moment PR #9 merges (D-025).

### Phase 3 — Skeleton
9. DONE 2026-10-20 (D-024). Humanoid, four-legged and bird rigs, test pose, page (PR #15).
   Monsters (limb-chain editor) not yet assigned.

### Phase 4 — Animation (assigned 2026-10-20, D-025)
10. First slice: idle, walk, run, attack, hit, faint for 2 legs, 4 legs and bird; one .glb; gate
    and Godot check; Step 4 page. 6+ legs and monsters later.

### Phase 5 — Sprites (assigned 2026-10-20, D-022)
7. Sprite mode A back end (PR #11): turnaround-sheet backs, face and anatomy pair gates, D-023
   sizes. Left: spur trim, real runs, PR body. Pair yield is low (1 of 18 sheets): measured and
   reported, not tuned further.

### Phase 6 — Library and batch (assigned 2026-10-20, D-025)
11. Library tab (resume, duplicate, trash), batch queue, step timings. PR opens when a slot frees.

### Phase 9 — Prompt generator (assigned 2026-10-20, D-022)
8. DONE 2026-10-20. Back end (PR #12) and page (PR #14).

Later phases are in `docs/ROADMAP.md` and start only when listed here.
