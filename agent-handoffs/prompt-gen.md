# prompt-gen handoff (Phase 9 back end, D-020)

Branch claude/prompt-gen, worktree asset-forge-wt/prompt-gen. Draft PR holds the work.

## Done
- Model: Qwen/Qwen3-1.7B (Apache-2.0 per HF card), bf16, greedy, thinking off.
- Env: models/envs/promptgen (uv, torch cu130 + transformers); weights in models/hf.
- src/asset_forge/prompts/: expand(idea, asset_type, target) -> str, fallback(), CLI
  (python -m asset_forge.prompts "idea" --type monster [--view back] [--fallback]).
  Model writes only the subject line; view/pose/background words are fixed in templates.py.
  The model runs in a subprocess (worker.py) so the app never imports torch.
- tests/test_prompts.py (13, model mocked). docs/LICENCES.md rows added.
- Proof: side-session-notes/.../prompt_gen.md (10 ideas, time, VRAM) - needs the GPU lock.

## Left
- Wire to UI (after PR #8 app shell merges): button "Expand my idea", editable result.
- Speed: each call loads the model (subprocess); a resident worker would cut load time.
- Not touched: web/, api.py, STATUS.md, DECISIONS.md.
