# Asset Forge: working rules for every Claude Code session

Python 3.12 app (FastAPI backend + a three.js page on localhost) that drives local generators
(ComfyUI or a dedicated env), headless Blender 5.2 and Godot 4.7.2 (export checks only). Read
this file, then your handoff (`agent-handoffs/<role>.md`), then the design
(`docs/superpowers/specs/2026-10-19-asset-forge-design.md`, the source of truth for what the
tool is), then `docs/STATUS.md` "Assigned items". The general rules every project shares live in
`~/.claude/CLAUDE.md` and the skills it names (`ask-the-director`, `ai-game-dev-playbook`,
`github-hygiene`, `game-architecture`, `art-qa-critic`, `ai-slop-art`); this file holds only
what is true for Asset Forge.

## Philosophy (permanent)

**Designed by a person, developed with AI, never designed by AI.** The director supplies vision,
taste and final judgement. Agents supply execution, evidence and honest pushback.

- **Every asset it makes drops straight into a game: good-looking, light to run, and fast to
  get.** Ugly, heavy or slow are the three ways this tool fails (director, 2026-10-19). A feature
  that makes any of them worse is cut, even if it works.
- **A roadmap item is context, not authorisation.** Start only what `docs/STATUS.md` lists as
  assigned. When an assigned task is done: stop, report with evidence, recommend the next step, wait.
- **Simplest viable option first.** Fewer screens, fewer settings, fewer files.
- **Challenge the director** when a request conflicts with the design or these rules. One
  paragraph, a better option, then do what the director decides.
- **Ask, don't ponder.** His calls are asked at once, the `ask-the-director` way, with labelled
  images for anything visual and a clip for anything that moves.

## Hard rules

1. **Local and free.** No paid API, credits or cloud generation (director, 2026-10-19). No spend
   without his written yes in `docs/DECISIONS.md`.
2. **Licences.** Every model, LoRA, node pack, library or asset allows commercial use and is
   listed in `docs/LICENCES.md` before use. Non-commercial or research-only is banned (Flux dev).
3. **Public repo.** No keys, tokens, personal paths or model weights in git. Machine paths live in
   the gitignored `config.local.toml` (template: `config.example.toml`).
4. **Never touch the Stability Matrix ComfyUI install**: no update, reinstall, second copy or
   switching it through comfy-mcp. Anything we need goes in our own env (`.venv/`, gitignored).
5. **Gates are code, not promises.** The export budgets and checks in the design (section 6) are
   enforced by the app and covered by tests; a model that fails a gate does not export.
6. **Every generated model is inspected** from five views, untextured and textured, with an
   anatomy count, before it reaches a board or the director; again after any mesh processing.
   Back sprites are real views from behind, never the front with the face removed.
7. **Proof before "done".** A change is done when its evidence is in the PR body.
8. **Change method after two failed fixes.** Gather different evidence and rethink.

## Machine rules (shared PC, one 12 GB GPU)

- One GPU job at a time (ComfyUI, Blender bakes/renders, local models). Free ComfyUI VRAM before
  a Blender bake. Do not run generation while the director is in a fullscreen game.
- Blender always `blender -b` (never a window). Godot only headless (`--headless`), isolated
  `APPDATA=<scratch>`. Never kill Blender, Godot or ComfyUI by image name; kill your own PID.
- Worktrees: `git worktree add -b claude/<topic> ../asset-forge-wt/<topic> origin/main`. Remove
  the worktree when the PR merges. More than four live is a violation.
- Only the lead edits `docs/STATUS.md` and `docs/DECISIONS.md`, in a docs-only board PR after
  each merge; every other PR states its board and log changes in its body.
- Stage files by name, never `git add -A`; never `git stash`.

## Tests and CI

`python -m pytest` (unit), `python -m pytest -m blender` (headless Blender integration, local
only), `ruff check .`. CI (`tests.yml`, job `test`) runs ruff and the unit suite with generation
mocked; no GPU in CI. Keep CI under 10 minutes. See the `forge-tests` skill.

## Sessions and context

- Fresh session at every task boundary; write `agent-handoffs/<role>.md` first (120-line cap,
  rewritten, never appended). Hand off at about 200k context; wait in the background only.
- End every turn with your state: working, running a check, awaiting director, blocked, available.

## Skills

Project skills live in `.claude/skills/forge-*` and extend the general ones; each has a
`references/learnings.md` with the evidence bar from `~/.claude/CLAUDE.md`. General lessons go
to the general skill's log so every project benefits.
