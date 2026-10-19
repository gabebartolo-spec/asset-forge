# Decisions log

Cap: 400 lines; oldest roll to `docs/archive/`. One decision per entry, newest first. A decision
that is not here does not exist. Format: date · id · who decided · the decision · why · what it
changes. Only the lead edits this file, from the "Board and log" section of merged PRs.

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
