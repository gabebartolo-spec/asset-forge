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
| Lead (s8) | working | board; critics; merges | this PR | 2026-10-20 |
| af-clean | working | item 5 (method B to 8/10; D-027) | #9 | 2026-10-20 |
| af-anim | working | item 10 (fix first, D-028; re-rig on #22) | #20 | 2026-10-20 |
| af-refdraw | working | item 4 follow-up (text-only reference drawer) | claude/ref-drawer | 2026-10-20 |
| af-monster | working | item 13 (monster skeleton + limb count) | claude/monster-rig | 2026-10-20 |
| af-proto | working | e2e run2 (goal: 80% critic pass) | claude/prototype | 2026-10-20 |

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
5. Step 2 Clean + gates (PR #9). Method B (multi-view + per-view colour match): 6/10. D-027:
   keep improving first; fix causes (registration, single part), bar 8/10, then realism critic.
6. DONE 2026-10-20. Export gate + headless Godot import check (PR #7).
12. Step 2 page + hand-over to Step 3, built now with Clean mocked; merges after #9 (D-026).

### Phase 3 — Skeleton
9. DONE 2026-10-20 (D-024). Humanoid, four-legged and bird rigs, test pose, page (PR #15).
13. Monsters: skeleton proposed from the mesh, limb-chain editor; the same limb counter checks
    Step 1 output (a 10-legged spider is re-rolled) (D-026).

### Phase 4 — Animation (assigned 2026-10-20, D-025)
10. First slice: idle, walk, run, attack, hit, faint for 2 legs, 4 legs and bird; one .glb; gate
    and Godot check; Step 4 page. 6+ legs and monsters later.

### Phase 5 — Sprites (assigned 2026-10-20, D-022)
7. DONE 2026-10-20 (back end, PR #11, D-023). Pair gates work; turnaround-sheet backs yield 0-1
   of 18, so backs move to the multi-view method once item 5 proves it.

### Phase 6 — Library and batch (assigned 2026-10-20, D-025)
11. DONE 2026-10-20 (PR #17). Clean joins the batch in item 12.

### Phase 9 — Prompt generator (assigned 2026-10-20, D-022)
8. DONE 2026-10-20. Back end (PR #12) and page (PR #14).

### Phase 10 — Cut out the subject (assigned 2026-10-20, D-031)
14. BiRefNet "Cut out the subject" step (lead builds it; see ROADMAP Phase 10).

Later phases are in `docs/ROADMAP.md` and start only when listed here.
