"""The graphics-card budget (D-030). Several jobs share the 12 GB card at once when their
declared video memory fits; CPU-only jobs (need 0) never wait.

Shared with tools/bakeoff/gpu_lock.py, other agents and older copies of this code:
- `models/gpu.lock/` exists while anyone holds the card.
- `owner.txt` inside it is an old-style holder (older code: mkdir, then owner.txt). It has the
  whole card; nothing new enters until it leaves, and it only enters an absent folder.
- `holder-<pid>-<token>.json` inside it is one new-style holder: owner, pid, vram_mb, exclusive.
  Written atomically (temp file + replace); a holder whose process is gone is removed.
- `models/gpu.lock.admit/` is a short mutex around read-sum-write, so two newcomers never both
  take the last free megabytes.

A holder enters when the sum of the declared needs plus its own fits the budget (default 11000
MB, `[gpu] budget_mb`), and, when nvidia-smi answers, its own need fits the card's live free
memory (so a program outside the budget, or a model left loaded, is respected).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

DEFAULT_BUDGET_MB = 11000

# Declared video memory per job type, in MB. Generators and SDXL are the measured whole-card
# peaks on this PC (nvidia-smi, so they include the desktop's share): docs/audits/
# bakeoff_2026-10-20.md, the ref-drawer run (10736 MB) and the prompt writer (about 4.2 GB).
# Blender clean-up, rigging, animation, measuring and sprite pixel work run on the CPU: 0.
# A job type not in this table takes the whole card (exclusive), the safe default.
VRAM_MB: dict[str, int] = {
    "generate:hi3dgen": 6800,
    "generate:triposg": 6300,
    "generate:step1x": 5800,
    "generate:triposr": 5400,
    "draw:sdxl": 10800,
    "clean:multiview": 11000,  # MV-Adapter views inside Clean (its VRAM_CAP_GB 11.0): whole card
    "expand:qwen": 4200,
    "clean": 0,  # remesh, decimate, merge, UV (Blender, CPU)
    "skeleton": 0,  # template fit, bind, weights (Blender, CPU)
    "animate": 0,  # procedural keys (Blender, CPU)
    "measure": 0,  # gates, five-view counts, silhouettes (Python)
    "sprite-post": 0,  # grid, palette, outline, QA (Python)
}


def shared_models_dir(repo: Path) -> Path:
    """The main checkout's gitignored models/ folder (weights, envs and gpu.lock), shared by
    every worktree: `FORGE_MODELS_DIR` if set, else found from the worktree's `.git` file, so
    both `.claude/worktrees/<name>` and `../asset-forge-wt/<topic>` checkouts use one lock."""
    env = os.environ.get("FORGE_MODELS_DIR")
    if env:
        return Path(env)
    git = repo / ".git"
    if git.is_file():  # a worktree: "gitdir: <main>/.git/worktrees/<name>"
        with contextlib.suppress(OSError, IndexError):
            line = git.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                return Path(line[7:].strip()).parents[2] / "models"
    return repo / "models"


def vram_need(kind: str | None) -> int | None:
    """MB for a job type, or None (exclusive) for a type the table does not know."""
    return VRAM_MB.get(kind) if kind else None


def query_card_mb() -> tuple[int, int] | None:
    """(free, total) MB of the first card from nvidia-smi, or None when it does not answer.
    Never opens a console window."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(  # noqa: S603
            [exe, "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True, creationflags=flags,
        ).stdout
        free, total = (int(x) for x in out.strip().splitlines()[0].split(","))
        return free, total
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # os.kill(pid, 0) would terminate the process on Windows
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            k32.GetExitCodeProcess(h, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_owner(lock: Path) -> str:
    """Who holds the card, in plain words (for 'Waiting for the graphics card (...)')."""
    names = [h["owner"] for h in _holders(lock)]
    f = lock / "owner.txt"
    if f.exists():
        with contextlib.suppress(OSError):
            names.insert(0, f.read_text(encoding="utf-8").strip())
    return ", ".join(n for n in names if n) or "another job"


def _holders(lock: Path, clean: bool = False) -> list[dict]:
    out = []
    try:
        files = sorted(lock.glob("holder-*.json"))
    except OSError:
        return out
    for f in files:
        try:
            h = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not pid_alive(int(h.get("pid", 0))):
            if clean:
                with contextlib.suppress(OSError):
                    f.unlink()
            continue
        out.append(h)
    return out


@contextlib.contextmanager
def _admit_mutex(lock: Path, poll_s: float) -> Iterator[None]:
    m = lock.with_name(lock.name + ".admit")
    while True:
        try:
            m.mkdir()
            break
        except FileExistsError:
            with contextlib.suppress(OSError):  # its holder died mid-admission
                if time.time() - m.stat().st_mtime > 10:
                    shutil.rmtree(m, ignore_errors=True)
                    continue
            time.sleep(min(poll_s, 0.05))
    try:
        yield
    finally:
        shutil.rmtree(m, ignore_errors=True)


def _try_enter(lock: Path, entry: dict, budget_mb: int, poll_s: float,
               card: Callable[[], tuple[int, int] | None]) -> tuple[Path | None, str]:
    """One admission attempt. Returns (holder file, "") or (None, why it must wait)."""
    need, exclusive = entry["vram_mb"], entry["exclusive"]
    live = None if exclusive else card()  # outside the mutex: nvidia-smi takes ~100 ms
    with _admit_mutex(lock, poll_s):
        if (lock / "owner.txt").exists():
            return None, "held"
        if lock.is_dir():
            others = _holders(lock, clean=True)
            if not others:
                with contextlib.suppress(OSError):  # an old-style holder may be starting
                    if time.time() - lock.stat().st_mtime < 2:
                        return None, "held"
        else:
            try:
                lock.mkdir(parents=False)
            except FileExistsError:
                return None, "held"
            others = []
        if exclusive and others:
            return None, "held"
        if any(h.get("exclusive") for h in others):
            return None, "held"
        used = sum(int(h.get("vram_mb", 0)) for h in others)
        if not exclusive and used + need > budget_mb:
            return None, "budget"
        if live is not None and need > live[0]:
            return None, "memory"
        f = lock / f"holder-{os.getpid()}-{secrets.token_hex(4)}.json"
        tmp = f.with_name("." + f.name + ".tmp")
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        os.replace(tmp, f)
        return f, ""


def _leave(lock: Path, holder: Path, poll_s: float) -> None:
    with _admit_mutex(lock, poll_s):
        with contextlib.suppress(FileNotFoundError):
            holder.unlink()
        if not _holders(lock, clean=True) and not (lock / "owner.txt").exists():
            for leftover in lock.glob(".holder-*.tmp"):
                with contextlib.suppress(OSError):
                    leftover.unlink()
            with contextlib.suppress(OSError):
                lock.rmdir()


@contextlib.contextmanager
def gpu_lock(
    lock: Path,
    owner: str,
    poll_s: float = 1.0,
    on_wait: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    *,
    vram_mb: int | None = None,
    budget_mb: int = DEFAULT_BUDGET_MB,
    make_room: Callable[[], None] | None = None,
    card: Callable[[], tuple[int, int] | None] | None = None,
) -> Iterator[None]:
    """Hold `vram_mb` of the card's budget while the block runs. `vram_mb=None` takes the whole
    card (the old one-at-a-time lock); 0 means CPU only and returns at once. `make_room` is
    called once when only the live free memory is short (e.g. to unload an idle model).
    The positional arguments are the old lock's (lock, owner, poll_s, on_wait, cancelled), so
    callers written before D-030 keep the whole card unchanged."""
    if vram_mb == 0:
        yield
        return
    exclusive = vram_mb is None or vram_mb >= budget_mb
    need = budget_mb if exclusive else int(vram_mb)
    entry = {"owner": owner, "pid": os.getpid(), "vram_mb": need, "exclusive": exclusive,
             "since": time.ctime()}
    card = card or query_card_mb
    lock.parent.mkdir(parents=True, exist_ok=True)
    roomed = False
    while True:
        holder, why = _try_enter(lock, entry, budget_mb, poll_s, card)
        if holder:
            break
        if why == "memory" and make_room and not roomed:
            roomed = True
            make_room()
            continue
        if on_wait:
            on_wait(lock_owner(lock) if why != "memory" else "another program")
        if cancelled and cancelled():
            raise InterruptedError("stopped while waiting for the graphics card")
        time.sleep(poll_s)
    try:
        yield
    finally:
        _leave(lock, holder, poll_s)
