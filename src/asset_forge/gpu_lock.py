"""One GPU job at a time. Same lock as tools/bakeoff/gpu_lock.py: the directory
`models/gpu.lock`, created atomically with mkdir, `owner.txt` names the holder, so the app, the
bake-off tools and other agents all queue behind each other."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path


def lock_owner(lock: Path) -> str:
    f = lock / "owner.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "another job"


@contextlib.contextmanager
def gpu_lock(
    lock: Path,
    owner: str,
    poll_s: float = 1.0,
    on_wait: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[None]:
    lock.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            lock.mkdir(parents=False)
            break
        except FileExistsError:
            if on_wait:
                on_wait(lock_owner(lock))
            if cancelled and cancelled():
                raise InterruptedError("stopped while waiting for the graphics card") from None
            time.sleep(poll_s)
    (lock / "owner.txt").write_text(f"{owner} pid={os.getpid()} since={time.ctime()}\n")
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            (lock / "owner.txt").unlink()
        with contextlib.suppress(OSError):
            lock.rmdir()
