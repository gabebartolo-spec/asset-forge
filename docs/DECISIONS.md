# Decisions log

Cap: 400 lines; oldest roll to `docs/archive/`. One decision per entry, newest first. A decision
that is not here does not exist. Format: date · id · who decided · the decision · why · what it
changes. Only the lead edits this file, from the "Board and log" section of merged PRs.

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
