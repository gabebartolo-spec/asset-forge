# Roadmap

Cap: 600 lines; finished phases roll to `docs/archive/`. Read by section. What the tool is lives
in `docs/superpowers/specs/2026-10-19-asset-forge-design.md`; this file owns order and gates.
A phase starts only when `docs/STATUS.md` lists its items.

## Phase 0 — Foundations
Deliverables: scaffold green on main; CI proven red on planted defects; licence register.
Gate: STATUS Phase 0 done.

## Phase 1 — Generator bake-off
Deliverables: bake-off report (design 5.2 bar). Gate: the director's pick in DECISIONS.md.

## Phase 2 — 3D: Generate and Clean, end to end
Deliverables: app shell (step screens, viewer, job store, one GPU queue); Generate; Clean
(rebuild, decimate, UV, bake); five-view inspection sheet; export gate; headless Godot import
check. Gate: three prompts (humanoid, monster, animal) export inside budget; director sees them.

## Phase 3 — Skeleton
Deliverables: humanoid template (SkeletonProfileHumanoid names), four-legged template, monster
limb-chain editor with draggable markers; binding with fallback weights; test pose.
Gate: the three Phase 2 models rigged and posed without broken weights; director sees clips.

## Phase 4 — Animation
Deliverables: idle, walk, run, attack, hit, faint for 2, 4, 6 and 8+ legs; no foot sliding.
Gate: clips for each body type pass the motion critic, then the director.

## Phase 5 — Sprites
Deliverables: Sprite mode A (draw + pixel-perfect processing + sprite QA), Southern Cross preset
(default) and GBA preset; mode B (render from a model, idle frames).
Gate: a Southern Cross front/back pair that drops into the game; director approval.

## Phase 6 — Library and batch
Deliverables: Library (resume any step, duplicate, trash), batch queue, step timings.
Gate: the speed targets in design section 6 measured and reported.

## Phase 7 — Optional local-AI QA check (after a working build; D-015)
Deliverables: design 5.6 (setting off by default, local vision model via Ollama, plain-words note,
never blocks). Gate: agreement with the critic agents on saved five-view sheets reported; the
director decides whether it ships on.

## Phase 8 — Claude MCP server (D-016)
Deliverables: design 5.7 (MCP tools over the backend job API for every step, sprite and Library
action). Gate: Claude makes one humanoid and one sprite end to end through MCP alone, and the
director can resume both in the UI.
