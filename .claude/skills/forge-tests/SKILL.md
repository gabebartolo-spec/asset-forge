---
name: forge-tests
description: How to run, add and debug Asset Forge's tests and CI - pytest markers (unit, blender, gpu), the fixture meshes and images, mocking the generator, headless Blender and Godot runs that never steal focus or clash with other agents, and keeping CI under 10 minutes. Extends the general game-architecture skill (test shape) with this repo's Python layout. Use it whenever you run or add a test, touch tests.yml, or see a failure that might not be your change's fault.
---

# Tests in Asset Forge

- **Unit** (`python -m pytest`): pure Python. Default run; CI runs exactly this plus `ruff check .`.
- **Blender** (`python -m pytest -m blender`): headless `blender -b --python ...` on tiny fixture
  meshes in `tests/fixtures/`. Local only. Blender path from `config.local.toml`.
- **GPU** (`python -m pytest -m gpu`): real generation. Local only, one at a time, never while the
  director is in a fullscreen game; free ComfyUI VRAM first.

Rules
- Every check that guards a gate gets a known-bad fixture that makes it fail (a mesh over
  budget, a sprite with a stray pixel, a back view that copies the front).
- Generation is behind one interface; tests use a fake that returns a fixture mesh or image.
- Seeds are pinned and written in the test; a flaky test is a seed to pin, not a rerun.
- Headless Godot import checks run with `--headless` and `APPDATA=<scratch>`; kill by PID only.
- CI target: under 10 minutes. Long or GPU work never goes in CI.

## Learnings

Proven findings live in `references/learnings.md`.
