# Handoff: gpu-pool (builder)

Date: 2026-10-20. State: done; PR #28 open and ready, CI running, Auto-fix on (lead merges). Branch `claude/gpu-pool`
(head 2853e66: budget lock + lead's Clean follow-up; PR body updated),
worktree `.claude/worktrees/confident-allen-f3502b`.

## Task (lead brief, director 2026-10-20: "why is there only 1 gpu queue? open as many as you can")
Replace the one-at-a-time `models/gpu.lock` with a VRAM budget (D-030 in the PR's Board and log).

## What was built
- `src/asset_forge/gpu_lock.py`: `gpu_lock(lock, owner, vram_mb, budget_mb=11000, ...)`.
  One `holder-<pid>-<token>.json` per holder inside `models/gpu.lock/` (atomic temp + replace),
  admission under a short `gpu.lock.admit/` mkdir mutex (stale after 10 s), dead-PID entries
  removed (ctypes on Windows; never `os.kill(pid, 0)` there). Enters when declared sum + own need
  <= budget and own need <= nvidia-smi free (CREATE_NO_WINDOW). `vram_mb=None` = whole card
  (exclusive); `0` = CPU, returns at once. `make_room` hook is called once when only live memory
  is short (the app passes `release_idea_writer`, the resident 4.2 GB Qwen writer).
- Old-style holders (older code: mkdir + `owner.txt`) still get the whole card; a young empty
  folder (< 2 s) is treated as an old holder starting. Old code waits while any new entry exists.
- `VRAM_MB` table (one place): hi3dgen 6800, triposg 6300, step1x 5800, triposr 5400, draw:sdxl
  10800, expand:qwen 4200; clean/skeleton/animate/measure/sprite-post 0. Unknown type = exclusive.
- Lead follow-up (2026-10-20): `gpu_lock` keeps the OLD positional order (lock, owner, poll_s,
  on_wait, cancelled); `vram_mb` is keyword-only, because clean.py (reverent-liskov worktree)
  calls `gpu_lock(path, "clean multiview", 5.0)`. Row `clean:multiview` 11000 (whole card;
  MV-Adapter VRAM_CAP_GB 11.0). Clean job = 0 MB; `steps.clean_command(..., gpu_lock_dir=)`
  adds `--gpu-lock DIR`. Wiring it into the Clean job waits for #9 (not in main yet).
- `shared_models_dir(repo)`: reads the worktree's `.git` file to find the main checkout. Fixed an
  old bug: from `.claude/worktrees/<name>` the old CLI and config used the worktree's own
  `models/` (a private lock nobody else saw).
- `jobqueue.GpuQueue`: a thread per job; card jobs admitted in press order (a waiting big job
  holds back later card jobs), CPU jobs start at once. `submit(..., need=...)`. `wait()` waits for
  `settled`; `Job.view()` (API/batch) reads "running" until settled (fixed a done-before-saved race).
- `api.py`/`library.py` pass needs: expand, draw, generate:<id>, batch = max(draw, generate).
- `tools/bakeoff/gpu_lock.py run <who> [--vram MB] -- cmd`: default stays exclusive.
- `[gpu] budget_mb` in config (Settings.gpu_budget_mb, config.example.toml).
- Docs: CLAUDE.md machine rule, design 4/5.7/9 lines, ROADMAP Phase 2, forge-tests GPU line.

## Evidence
- Unit: full suite 206 passed before the path fix; then gpu/queue suites 16 passed; ruff clean.
  New `tests/test_gpu_budget.py` (11 tests). conftest autouse disables nvidia-smi in tests.
- Real proof (notes folder `gpu_pool_proof/`): A and B (--vram 256, real CUDA allocs on the
  4070 SUPER) overlapped 17:52:16.3-17:52:30.9; C (no --vram) waited "for proofB, proofA" and
  started 17:52:48.8. Live lock: `--vram 256` waited behind af-clean's old-style holder for 10 s;
  `--vram 0` entered at once; no entry left behind.

## Not exercised
- Two real generators at once in the app (card was busy with af-clean). Needs for Blender
  bakes/renders are not in the table (exclusive by default) until measured.

## Running jobs / open decisions
- None running. No open decisions. Unfinished changes: none.
- Finding for the lead's learnings (forge-proof-evidence): the live-lock run caught the private
  worktree lock that the unit tests could not see.

## Next
- #9 author: submit Clean with step "clean" (0 MB), pass `gpu_lock_dir=settings.lock_dir`, and
  have clean.py pass `vram_mb=vram_need("clean:multiview")`.
- Lead: merge; record D-030; tell running agents they may pass `--vram <MB>` from the table.
- Follow-up: measure Blender bake/render VRAM and add rows; forge-tests "never while the director
  is in a fullscreen game" contradicts the rulebook (lead's call).
