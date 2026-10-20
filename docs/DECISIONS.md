# Decisions log

Cap: 400 lines; oldest roll to `docs/archive/`. One decision per entry, newest first. A decision
that is not here does not exist. Format: date · id · who decided · the decision · why · what it
changes. Only the lead edits this file, from the "Board and log" section of merged PRs.

## 2026-10-20 · D-032 · Director · Forge makes every kind of 3D asset, and Godot-direct modelling stays on the roadmap
His words: "we want this program to be adept at all 3d models, gear, objects, vehicles, buildings" and
"modelling in godot directly may be useful, dont abandon that thread, we are going to model more than just
monsters in the game". Changes: design section 1 scope and proposed hard-surface budgets (section 6),
ROADMAP Phase 12 (types, bake-off, Godot-direct modelling through the Claude MCP, rebuild-from-generated,
building kits). Lead's call: Godot-direct modelling is written by the director's Claude session via
Phase 8, not by a paid API inside the app, so "local and free" stands; budgets are proposals until the
bake-off. Supersedes the D-031 line that put Claude-built models outside the design.

## 2026-10-20 · D-031 · Director · Take the good ideas from the community posts; add background cut-out
His words: "assess the claims in all the images I linked you, take whats good from it", "our forge also
needs the ability to remove backgrounds/cut the subject out of the image", "well incorporate all the good
ideas into the roadmap". Changes: roadmap Phase 10 (cut-out, assigned) and Phase 11 (delighting,
Z-Image-Turbo, wireframe and height, user side/back pictures, send-back-with-notes, KTX2); skipped ideas
and why are listed there. Phase 11 items start only when STATUS lists them.

## 2026-10-20 · D-030 · Director · As many GPU jobs at once as fit in VRAM
His words: "why is there only 1 gpu queue? open as many as you can". Changes: PR #28, the lock is a
VRAM budget (each job declares its need, about 11 of 12 GB), CPU-only work (Blender, tests) takes no
lock; RULEBOOK and shared-machine-rules updated.

## 2026-10-20 · D-029 · Director · No subagents; every helper is a fresh session
His words: "no more subagents, if you need a helper you spawn a fresh session" and "seperate
sessions grouped properly in the toolbar". Changes: every builder and critic is a start_session
session in its own worktree, filed in the "Asset Forge" sidebar group (RULEBOOK; CLAUDE.md, PR #23).

## 2026-10-20 · D-028 · Director · Animation clips: fix first
Asked whether the PR #20 clips ship. His answer: "Fix first" on person walk, fox walk, bird walk,
and attack/faint. Changes: #20 stays open; it re-rigs on the #22 joints, makes previews_v4 and
passes a fresh motion critic before he sees the clips again.

## 2026-10-20 · D-027 · Director · Clean colour: keep improving first
Asked: ship the 6/10 multi-view colour now, keep improving, or shape only. His answer: "Keep
improving first". Changes: PR #9 stays open; a fresh Clean builder targets the causes behind the
4 fails (picture-to-mesh registration, single-part mesh, fox chest and front legs, greaves) with
a bar of 8/10 and a fresh realism critic before merge; step2-page (item 12) still merges after #9.

## 2026-10-20 · D-026 · Director · Anything that can run in parallel, runs
His words: "if theres anything you can work on in parrelal then do it". Changes: item 12 (Step 2
page + hand-over) starts now against PR #9's script interface with Clean mocked, merging after #9;
Phase 3 monsters (limb-chain editor) and a Step 1 limb-count check start now. Lead calls logged
here: animation clips in place with move speeds in clips.json; loops set by a Godot import sidecar
(names unchanged); gait speeds scale with leg length (Froude), no step-time floors.

## 2026-10-20 · D-023 · Director · Southern Cross sprite sizes
Southern Cross art 80 px, exported 2x = 160 px for front AND back, file names UPPERCASE; GBA
unchanged (PR #11). Sprite backs by turnaround sheet yielded 0-1 of 18: the back draw is replaced
by a multi-view method in a later slice.

## 2026-10-20 · D-025 · Director · Work on several phases at once
His words: "get to work / work on multiple phases at once, get more efficient". Changes: Phase 4
Animation (first slice: 2 legs, 4 legs, bird) and Phase 6 Library and batch start now beside the
Phase 2 and Phase 5 finishes. Limits kept: one GPU job at a time (models/gpu.lock), at most 3 open
PRs (Library waits on its branch for a slot), critic gates unchanged. Phases 7 and 8 still wait for
a working build.

## 2026-10-20 · D-024 · Lead · Skeleton started early; light humanoid rig
Director "Start now" on Skeleton before PR #9 merged, so Step 3 was built on copied cleaned
models (PR #15). Humanoid = the 23 required SkeletonProfileHumanoid bones only, mitt hands (light
to run); bird = neck/tail template with 2 legs and wing bones, chosen by counting legs on the
ground; at most 4 bone influences per vertex. The Step 2 -> Step 3 hand-over follows PR #9.

## 2026-10-20 · D-022 · Director · Go faster: later phases run in parallel
His words, on a 13-21 agent-hour estimate: "thats absurd. do it faster", then "faster!". Asked
which phases start; answer "Two now, Skeleton next". Changes: Phase 5 Sprites mode A and Phase 9
Prompt generator start now beside the Phase 2 fixes; Phase 3 Skeleton (humanoid + four-legged)
starts when PR #9 merges. Critic gates stay; reviews are batched.

## 2026-10-20 · D-021 · Lead · Model front is glTF +Z (Blender -Y)
Why: Godot 4's model front (MODEL_FRONT) is +Z in glTF, which is Blender -Y; design 5.2 said
"+Y forward" and the clean step faced literal +Y. Changes: clean.py faces Blender -Y before export
(test in PR #9); design 5.2 Step 2 corrected there. Default heights (humanoid 1.8 m, monster
2.0 m, animal 0.5 m) stay editable per asset.

## 2026-10-20 · D-020 · Director · Prompt generator ("Expand my idea")
His words: "roadmap item: add a prompt generator". Changes: ROADMAP Phase 9; a local model writes
the full image prompt from a few words, shown to edit before generating. Built with Qwen3-1.7B
(Apache-2.0, PR #12).

## 2026-10-20 · D-019 · Director · Step 1 menu: Hi3DGen, then TripoSG
Asked which bake-off passers go on the Step 1 menu and in what order (PR #6). Answer: Hi3DGen
first (preselected), then TripoSG. Step1X-3D and TripoSR are off the menu.

## 2026-10-20 · D-018 · Director · A generator menu on every run
Asked how the app should offer the generators that pass the bake-off: a default plus "try
another", choose every time, or one only. Answer: "Choose every time". Changes: Step 1 shows a
generator menu on every run listing every candidate that passes the bar (top one preselected);
every listed generator must pass the Clean-step tests (design 5.2, roadmap Phase 2). The bake-off
question becomes which passing models go on the menu and in what order (D-019).

## 2026-10-20 · D-017 · Director · Direct3D-S2 dropped; Hi3DGen gets one low-VRAM try
Asked (to go faster): drop Hi3DGen (13 GB peak) and Direct3D-S2 (20 GB, ~14 min a model), both
over the 12 GB card in testing? Answer: "drop direct 3d only". Changes: Direct3D-S2 leaves the
bake-off (fails the 12 GB / 3 min bar as measured); Hi3DGen gets one bounded attempt to fit 12 GB.

## 2026-10-20 · D-016 · Director · A Claude MCP server to operate the app
His words: "add to roadmap: claude mcp so you can operate the program". Changes: Phase 8 in the
roadmap; design 5.7. Built on the same backend job API the UI uses, so it adds no second code path.

## 2026-10-20 · D-015 · Director · Optional local-AI QA check, built last
His words: "add an optional feature to the program which loads a local model to QA, we can
implement it and test it later once all the other features are in a working build". Changes: a
Phase 7 item; design 5.6. Off by default; it warns in plain words and never blocks or edits a
model (the measured checks stay the gate). No trial in the bake-off.

## 2026-10-20 · D-014 · Director · Built for a normal person with no tech skills
His words: "the target demographic is normal person with no advanced tech skills or knowledge".
Changes: the UI gate (D-013) is judged as that person: plain words on screen (no "tris",
"seed", "remesh" on the main path; numbers shown as good/too heavy with the limit; VRAM is shown,
director: "i know what vram is, include it"),
errors say what happened and the one click that fixes it, and the first-use walk-through is
done by an agent briefed as a non-technical user.
Asked the same day: will others install it on their own PCs? Answer: only on his PC. So the
bake-off bar is unchanged (12 GB card, set up once by us); no installer or redistribution work.

## 2026-10-20 · D-013 · Director · The app's UI is clean and intuitive
His words: "make sure the programs UI is clean and intuitive". Changes: a UI gate in design
section 6: every screen passes a fresh screen-critic review and a first-use walk-through (a new
agent reaches the step's goal from the screen alone, no docs) before he sees it. Applies from the
first app screen (after the bake-off); the bake-off itself has no UI.

## 2026-10-20 · D-012 · Lead · Generators run in our own per-model envs
Why: the Stability Matrix ComfyUI folder was not found, CLAUDE.md forbids touching it, and the
cleared candidates (TripoSG, TripoSR, Hi3DGen, Direct3D-S2, Step1X-3D) are plain Python repos.
Changes: each generator gets a uv env `models/envs/<name>`, source `models/src/<name>`, weights
under `models/hf` (all gitignored), driven by `tools/bakeoff/` adapters behind one contract; one
GPU job at a time through `models/gpu.lock`. ComfyUI stays optional for the sprite tab.

## 2026-10-20 · D-011 · Director · Stable Fast 3D skipped
Asked: SF3D's weights are gated (Hugging Face sign-in, accept Stability's Community licence);
include it? Answer: skip SF3D. Changes: SF3D and SPAR3D leave the bake-off; their licence rows
stay CLEARED on paper but unused.

## 2026-10-20 · D-010 · Director · Hunyuan 3D dropped from the bake-off
Asked: keep Hunyuan (EU/UK/South Korea output ban) in the bake-off, flagged, or drop it now?
Answer: drop it now. Why: every asset must ship in any market. Changes: Hunyuan 2.x and the kijai
wrapper are BANNED; the bake-off uses only worldwide-licensed models.

## 2026-10-20 · D-009 · Lead · Licence register verdicts; Hunyuan held
Why: the Hunyuan 3D licence (§5c) bans using or distributing its Output outside the Territory
(world minus EU, UK, South Korea), so its assets could not ship in a game sold there. This
supersedes the D-008 line "Hunyuan allowed in Australia". Changes: Hunyuan rows are HELD until
the director decides; TRELLIS and every pack with nvdiffrast/diffoctreerast are BANNED; both
Civitai pixel items are BANNED (unverifiable or no-sale terms); `pixel-art-xl` and SDXL CLEARED.

## 2026-10-19 · D-008 · Lead (director may overrule) · Calls after the builder check
Why: settle builder questions without changing what gets built. Changes: design section 9 lists
them (8k monster budget editable, limb-chain editor first, no auto re-seed, Godot 4.7.2, bake-off
bar, Hunyuan allowed in Australia, one GPU queue).

## 2026-10-19 · D-007 · Director · Default sprite preset is Southern Cross
Essentials v21.1 Gen 9 Pack: 96x96 art, no 16-colour limit, front 2x / back 3x. GBA is a preset.

## 2026-10-19 · D-006 · Director · Name Asset Forge; public repo; the pillar
"Every asset it makes drops straight into a game: good-looking, light to run, and fast to get."
Public means GitHub enforces branch protection; nothing private or machine-specific is committed.

## 2026-10-19 · D-005 · Director · The tool animates
He cannot animate. Every rigged model gets idle, walk, run, attack, hit, faint (procedural).

## 2026-10-19 · D-004 · Director · Step-by-step flow (mockup B)
One screen per step with a big viewer, Next and Redo.

## 2026-10-19 · D-003 · Director · Sprites both ways
Drawn from text/image, and rendered from a 3D model.

## 2026-10-19 · D-002 · Director · Local and free generation only
No paid APIs (Tripo, Retro Diffusion, Meshy) in this tool.

## 2026-10-19 · D-001 · Director · Asset Forge is started with the shared kickoff scaffold
Why: project-kickoff produced the process skeleton; the Godot test harness was replaced with
pytest + ruff because this is a Python tool. Changes: the first commit.
