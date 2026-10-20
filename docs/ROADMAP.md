# Roadmap

Cap: 600 lines; finished phases roll to `docs/archive/`. Read by section. What the tool is lives
in `docs/superpowers/specs/2026-10-19-asset-forge-design.md`; this file owns order and gates.
A phase starts only when `docs/STATUS.md` lists its items.

## Phase 0 — Foundations
Deliverables: scaffold green on main; CI proven red on planted defects; licence register.
Gate: STATUS Phase 0 done.

## Phase 1 — Generator bake-off
Deliverables: bake-off report (design 5.2 bar). Gate: the director's menu (which passing
generators, in what order; D-018, D-019) in DECISIONS.md.

## Phase 2 — 3D: Generate and Clean, end to end
Deliverables: app shell (step screens, viewer, job store, GPU budget queue); Generate with the
generator menu (every generator on the D-019 menu behind one interface, top preselected; D-018);
Clean
(rebuild, decimate, UV, bake); five-view inspection sheet; export gate; headless Godot import
check. Gate: three prompts (humanoid, monster, animal) export inside budget through every
generator on the menu (each passes the Clean-step tests); director sees them.

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

## Phase 9 — Prompt generator (director, 2026-10-20, D-020)
His words: "roadmap item: add a prompt generator". Deliverables: a prompt generator on the
Step 1 and sprite text boxes: the user types a few words and a local model writes the full
prompt the image step needs (pose, view, plain background), shown to edit before generating
(D-020: "Expand my idea"). Local and free like everything else.
Gate: the director uses it to start one model and one sprite; screen-critic and first-use
walk-through pass. Order among later phases is the director's call.

## Phase 10 — Cut out the subject (director, 2026-10-20, D-031; assigned now)
His words: "our forge also needs the ability to remove backgrounds/cut the subject out of the image".
Deliverables: a "Cut out the subject" step on every uploaded or drawn picture (before/after, "Cut
again"), BiRefNet (MIT; code from GitHub, weights from Hugging Face, own env, no remote code), the
plain-background cut kept as the quick path, the one-subject check after it (draw: PR #30).
Gate: 10 real photos with busy backgrounds cut cleanly; LICENCES.md row; screen-critic passes.

## Phase 11 — Quality ideas from the community review (D-031; each starts only when listed in STATUS)
Source: r/aigamedev posts the director shared, 2026-10-20 (assessed in the lead handoff).
- Delight the reference (Marigold intrinsic decomposition, RAIL++-M licence: read it first), then
  project colour: tackles baked studio lighting behind the pale foxes. Gate: fox and humanoid colour
  scores rise on the 10 sheets, else dropped.
- Z-Image-Turbo (Apache 2.0) against SDXL as the reference drawer: single-subject rate, time, VRAM
  on the 5 bake-off prompts; director picks if it wins.
- Wireframe toggle in the viewer and a real-height field on Step 1 (small page change).
- Optional side and back reference pictures supplied by the user (better colour than invented views).
- "Send back with notes" on a step (a Redo that takes a note), designed with Phase 8's Claude MCP queue.
- KTX2 textures: only if the Godot import check shows a size or load-time gain.
Not adopted (reasons in D-031): TRELLIS.2 (nvdiffrast banned, 24 GB), three.js models (cannot export to Godot);
Claude-built Godot CSG models moved to Phase 12 (D-032); tree leaf cards and armour kits (outside the design).

## Phase 12 — Every kind of 3D asset: gear, props, vehicles, buildings (director, 2026-10-20, D-032)
His words: "we want this program to be adept at all 3d models, gear, objects, vehicles, buildings"
and "modelling in godot directly may be useful, dont abandon that thread, we are going to model more
than just monsters in the game". Deliverables, in order, each starting only when STATUS lists it:
1. Types Prop/gear, Vehicle, Building in Step 1: per-type reference-drawing views, per-type budgets
   (design section 6), Clean that keeps hard edges and flat faces (the creature rebuild rounds them),
   a static or by-parts export (no skeleton), the same gates and Godot import check.
2. Bake-off for hard-surface: the Hi3DGen and TripoSG menu on 5 prompts (a sword, a crate, a car, a hut,
   a robot), scored on the same five-view inspection; the director picks.
3. Godot-direct modelling ("Build in code"): Claude, operating Forge through the Phase 8 MCP, writes a
   Godot CSG or generated-mesh scene (or a Blender script) from a reference or five-view sheet; Forge runs
   it headless, bakes a .glb (Godot's GLTF export, to be verified), applies the gates and shows the
   five views. Fits vehicles, buildings, robots, props; not organic creatures (the community poster's
   own caveat). Not a paid API inside the app: the director's own Claude session does the writing, as in
   Phase 8, so hard rule 1 (local and free) holds.
4. Rebuild-from-generated: generate a model from a picture, then Claude rebuilds it as a clean procedural
   model with the needed improvements; compare against the raw model on the same views.
5. Modular kits for buildings (walls, roofs, doors that snap together) so a town stays light to run.
Gate: one gear piece, one vehicle and one building exported inside their budgets, Godot-green, five-view
inspected, and a fresh realism critic passes; director sees them.
