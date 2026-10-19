# Handoff: clean-step (PR #9, builder), rewritten 2026-10-20
State: fixing the critic's 9 FIX sheets. Branch claude/clean-step, worktree asset-forge-wt/clean-step.
Done in code (blender/clean.py, tools/clean/run_all.py):
- Facing: humanoid/monster by GENERATOR_FRONT_YAW (both generators measured: raw faces Blender -Y,
  yaw 0). Animals: still outline (profile, margin >= 0.10 or exit), because hi3dgen animals do not
  keep the reference view as front (fox profile faces +Y side, bird head-on).
- Colour: projection only onto texels facing the reference camera (ray test); everything else a
  3D Gaussian normal-weighted blend (blend_field), no mirror.
- Sheets rendered inside clean.py with ONE camera set for raw + clean (shared world frame).
- Forward = Blender -Y = glTF +Z (D-021); export_glb(); design 5.2 sentence replaced.
- Heights in run_all: humanoid 1.8, fox 0.40, bird 0.14, others default.
- Tests: tests/test_clean_forward.py (+ fixtures/forward_probe.py), blender-marked, local only.
  Failing first on old script: facing test (-0.177) and unseen-colour test failed; export test
  passed on old (export was right, facing was wrong).
Left: full 10-model run, check sheets, PR body, CI.
