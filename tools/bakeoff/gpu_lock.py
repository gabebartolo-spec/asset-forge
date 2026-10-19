"""One GPU job at a time (CLAUDE.md machine rules).

The lock is a directory, `models/gpu.lock`, created atomically with mkdir. Its `owner.txt` names
the holder. Use it from Python (`with gpu_lock("who"):`) or the shell:

    python tools/bakeoff/gpu_lock.py run "who" -- <command ...>
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _models_dir() -> Path:
    # Worktrees share the main checkout's gitignored models/ folder.
    env = os.environ.get("FORGE_MODELS_DIR")
    if env:
        return Path(env)
    main = REPO.parent.parent / "asset-forge" / "models"
    return main if main.is_dir() else REPO / "models"


LOCK = _models_dir() / "gpu.lock"


@contextlib.contextmanager
def gpu_lock(owner: str, poll_s: float = 5.0):
    waited = False
    while True:
        try:
            LOCK.mkdir(parents=False)
            break
        except FileExistsError:
            if not waited:
                held = (LOCK / "owner.txt").read_text() if (LOCK / "owner.txt").exists() else "?"
                print(f"[gpu_lock] waiting for {held.strip()}", file=sys.stderr, flush=True)
                waited = True
            time.sleep(poll_s)
    (LOCK / "owner.txt").write_text(f"{owner} pid={os.getpid()} since={time.ctime()}\n")
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            (LOCK / "owner.txt").unlink()
        with contextlib.suppress(OSError):
            LOCK.rmdir()


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[0] != "run" or argv[2] != "--":
        print(__doc__)
        return 2
    with gpu_lock(argv[1]):
        return subprocess.call(argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
