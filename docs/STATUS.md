# Status board

Cap: 150 lines. Edited only by the lead, in a board PR after each merge, from the merged PR's
"Board and log" section. History rolls to `docs/archive/status_<month>.md`.

## Phase
Current phase: **1 — Generator bake-off**. Phase 0 gate met 2026-10-20
(`docs/audits/kickoff_gate.md`), signed by the lead.

## Agents

| Agent | State | Item | Branch / PR | Since |
|-------|-------|------|-------------|-------|
| Lead | available | item 3 bake-off next (Hunyuan out, D-010) | — | 2026-10-20 |

States: working · running a check · awaiting director · blocked · available.

## Assigned items (in order; an item starts only when it is listed here)

### Phase 0 (assigned by the director, 2026-10-19: "set it up so i can begin development")
1. DONE 2026-10-20. Lead: prove the gate with throwaway PRs, each closed unmerged after it goes red: a failing
   unit test, a ruff error, a planted `FORGE_TEST_SECRET_` + 16 characters. Record run ids in
   `docs/audits/kickoff_gate.md`.
2. DONE 2026-10-20 (Hunyuan dropped, D-010). Lead: `docs/LICENCES.md` rows for every candidate generator, checkpoint and LoRA already on
   the machine (design section 4), with licence and verdict.

### Phase 1 — Generator bake-off (design 5.2; result goes to the director before anything else)
3. Bake-off script and report: five prompts through every qualifying local image-to-3D model
   (and the text-to-image front-end), with time, peak VRAM, licence, and five-view sheets. The
   director picks the generator. Log the pick as a decision.

Later phases are in `docs/ROADMAP.md` and start only when listed here.
