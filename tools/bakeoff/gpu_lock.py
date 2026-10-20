"""The graphics-card lock for tools and agents (D-030; same folder and rules as the app,
src/asset_forge/gpu_lock.py).

Without `--vram` a holder takes the whole card, as before: older callers stay safe. With
`--vram MB` it holds only that share of the budget, so jobs that fit run together; `--vram 0`
is a CPU-only job that never waits. Use it from Python (`with gpu_lock("who", vram_mb=6800):`)
or the shell:

    python tools/bakeoff/gpu_lock.py run "who" [--vram MB] -- <command ...>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from asset_forge.gpu_lock import DEFAULT_BUDGET_MB, shared_models_dir  # noqa: E402
from asset_forge.gpu_lock import gpu_lock as _budget_lock  # noqa: E402


def _models_dir() -> Path:
    # Worktrees share the main checkout's gitignored models/ folder.
    return shared_models_dir(REPO)


def _budget() -> int:
    try:
        import tomllib
    except ImportError:  # an older env python (before 3.11)
        return DEFAULT_BUDGET_MB
    main = _models_dir().parent
    for cfg in (REPO / "config.local.toml", main / "config.local.toml"):
        if cfg.is_file():
            return int(tomllib.loads(cfg.read_text(encoding="utf-8"))
                       .get("gpu", {}).get("budget_mb", DEFAULT_BUDGET_MB))
    return DEFAULT_BUDGET_MB


LOCK = _models_dir() / "gpu.lock"


def gpu_lock(owner: str, poll_s: float = 5.0, vram_mb: int | None = None):
    said = []

    def on_wait(held: str) -> None:
        if not said:
            print(f"[gpu_lock] waiting for {held}", file=sys.stderr, flush=True)
            said.append(held)

    return _budget_lock(LOCK, owner, poll_s, on_wait, vram_mb=vram_mb, budget_mb=_budget())


def main(argv: list[str]) -> int:
    vram = None
    if len(argv) >= 4 and argv[0] == "run" and argv[2] == "--vram":
        try:
            vram = int(argv[3])
        except ValueError:
            print(__doc__)
            return 2
        argv = argv[:2] + argv[4:]
    if len(argv) < 4 or argv[0] != "run" or argv[2] != "--":
        print(__doc__)
        return 2
    with gpu_lock(argv[1], vram_mb=vram):
        return subprocess.call(argv[3:])  # noqa: S603


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
