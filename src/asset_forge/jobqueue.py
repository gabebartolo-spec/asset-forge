"""One GPU job queue. Jobs run one at a time, in the order they were pressed, and each holds
`models/gpu.lock` while it runs so it also waits for Blender, ComfyUI or an agent's job."""

from __future__ import annotations

import queue
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .gpu_lock import gpu_lock

QUEUED, WAITING, RUNNING, DONE, FAILED = "queued", "waiting", "running", "done", "failed"
ACTIVE = (QUEUED, WAITING, RUNNING)


@dataclass
class Job:
    id: str
    asset_id: str
    step: str
    run: Callable[[Job], dict | None]
    state: str = QUEUED
    message: str = "Waiting for its turn"
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: dict | None = None
    persist: Callable[[Job], None] | None = None
    settled: bool = False  # the end state is on disk too (the Library waits for this)

    def set_message(self, text: str) -> None:
        self.message = text
        self.save()

    def save(self) -> None:
        if self.persist:
            self.persist(self)

    def public(self) -> dict:
        end = self.finished or time.time()
        return {
            "id": self.id, "asset_id": self.asset_id, "step": self.step, "state": self.state,
            "message": self.message, "error": self.error, "created": self.created,
            "started": self.started, "finished": self.finished,
            "elapsed_s": round(end - self.started, 1) if self.started else 0.0,
            "result": self.result,
        }


class GpuQueue:
    def __init__(self, lock_dir: Path, persist: Callable[[Job], None] | None = None,
                 lock_poll_s: float = 1.0) -> None:
        self.lock_dir = lock_dir
        self.persist = persist
        self.lock_poll_s = lock_poll_s
        self.jobs: dict[str, Job] = {}
        self._q: queue.Queue[Job | None] = queue.Queue()
        self._counter = 0
        self._mu = threading.Lock()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="gpu-queue")
        self._worker.start()

    def submit(self, asset_id: str, step: str, run: Callable[[Job], dict | None]) -> Job:
        with self._mu:
            self._counter += 1
            job = Job(f"j{self._counter}-{int(time.time())}", asset_id, step, run)
            job.persist = self.persist
            self.jobs[job.id] = job
        job.save()
        self._q.put(job)
        return job

    def ahead_of(self, job: Job) -> int:
        """How many jobs are in front of this one (0 = it is next or running)."""
        active = sorted((j for j in self.jobs.values() if j.state in ACTIVE),
                        key=lambda j: j.created)
        return active.index(job) if job in active else 0

    def wait(self, job_id: str, timeout: float = 30.0) -> Job:
        job = self.jobs[job_id]
        end = time.time() + timeout
        while job.state in ACTIVE and time.time() < end:
            time.sleep(0.02)
        return job

    def shutdown(self) -> None:
        self._stop.set()
        self._q.put(None)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self._q.get()
            if job is None:
                return
            self._run_one(job)

    def _run_one(self, job: Job) -> None:
        def on_wait(owner: str) -> None:
            if job.state != WAITING:
                job.state = WAITING
                job.message = f"Waiting for the graphics card ({owner} is using it)"
                job.save()

        end, words = FAILED, "Stopped"
        try:
            with gpu_lock(self.lock_dir, f"asset-forge:{job.asset_id}", self.lock_poll_s,
                          on_wait, self._stop.is_set):
                job.state = RUNNING
                job.started = time.time()
                job.message = "Starting"
                job.save()
                job.result = job.run(job)
                end, words = DONE, "Done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job.error = _plain(e)  # before the state flips: waiters read both
            end, words = FAILED, job.error
        finally:
            job.finished = time.time()
            self._settle(job, end, words)

    @staticmethod
    def _settle(job: Job, end: str, words: str) -> None:
        """Write the end state to disk (status, timings) first, then show it: anyone who sees
        "done" or "failed" can read the asset's files at once (the Library's busy check, the
        page's next step)."""
        try:
            replace(job, state=end, message=words).save()
        finally:
            job.message = words
            job.state = end
            job.settled = True


def _plain(e: Exception) -> str:
    """Our own errors are already plain words; anything else gets a generic line (the detail
    is in the console and the generator log)."""
    from .animate import AnimFailed
    from .draw import DrawError
    from .export import ExportRefused
    from .generators import GeneratorError
    from .skeleton import RigFailed

    if isinstance(e, GeneratorError | DrawError | InterruptedError | RigFailed | AnimFailed):
        return str(e)
    if isinstance(e, ExportRefused):
        return "This model cannot be exported yet: " + " ".join(e.reasons)
    return "Something went wrong. Press Redo to try again."
