# Status board

Cap: 150 lines. Edited only by the lead, in a board PR after each merge, from the merged PR's
"Board and log" section. History rolls to `docs/archive/status_<month>.md`.

## Phase
Current phase: **2 — Generate and Clean**, with Phase 5 (Sprites mode A) and Phase 9 (Prompt
generator) running in parallel (director, 2026-10-20, D-022). Phase 1 done 2026-10-20 (D-019).

## Agents

| Agent | State | Item | Branch / PR | Since |
|-------|-------|------|-------------|-------|
| Lead | running a check | items 4-9; board | this PR | 2026-10-20 |
| app-shell builder | working | item 4 (screen-critic round 2 fixes) | #8 | 2026-10-20 |
| clean builder | working | item 5 (colour fix round 2) | #9 | 2026-10-20 |
| sprites builder | working | item 7 (art-QA fixes, speed) | #11 | 2026-10-20 |

States: working · running a check · awaiting director · blocked · available.

## Assigned items (in order; an item starts only when it is listed here)

### Phase 0 (assigned by the director, 2026-10-19: "set it up so i can begin development")
1. DONE 2026-10-20. Gate proved with throwaway PRs (`docs/audits/kickoff_gate.md`).
2. DONE 2026-10-20 (Hunyuan dropped, D-010). Licence rows for every candidate.

### Phase 1 — Generator bake-off
3. DONE 2026-10-20 (D-019: Hi3DGen then TripoSG; PR #6).

### Phase 2 — Generate and Clean (assigned 2026-10-20: "Yes, split it in two", "spawn 1 more")
4. App shell + Step 1 Generate + generator menu (PR #8). Live GPU run and first-use walk-through
   passed; screen-critic round 2 fixes in progress. Then the director sees Step 1. Follow-up:
   text-only input and a textured view (design 5.2) once the sprite SDXL draw lands.
5. Step 2 Clean + gates (PR #9). Forward axis D-021. Fidelity check round 1: 4 of 10 pass; colour
   fix round 2 in progress (two failed fixes means a change of method).
6. DONE 2026-10-20. Export gate + headless Godot import check (PR #7).

### Phase 5 — Sprites (assigned 2026-10-20, D-022)
7. Sprite mode A back end: draw, pixel-perfect processing, sprite QA, Southern Cross + GBA
   presets (PR #11). Art-QA round 1: all four FIX; fixes and a pair under 60 s in progress.

### Phase 9 — Prompt generator (assigned 2026-10-20, D-022)
8. DONE 2026-10-20 (back end). "Expand my idea" writer, Qwen3-1.7B (PR #12). UI after #8 merges.

### Next (assigned, starts on a trigger)
9. Phase 3 Skeleton (humanoid + four-legged templates) starts the moment PR #9 merges (D-022).

Later phases are in `docs/ROADMAP.md` and start only when listed here.
