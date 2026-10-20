"""The job queue (D-030). Each job runs on its own thread and holds its declared share of the
graphics-card budget (`models/gpu.lock`, see gpu_lock.py) while it runs, so jobs that fit run
together and still respect Blender, ComfyUI and other agents' jobs. Jobs that use the card
start in the order they were pressed (a job that does not fit yet holds back the ones behind
it); CPU-only jobs (need 0) start at once."""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .gpu_lock import DEFAULT_BUDGET_MB, gpu_lock, vram_need

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
    vram_mb: int | None = None  # declared need; None = the whole card
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

    def view(self) -> dict:
        """What the page sees: a finished job still reads as running until its end state, its
        result and its timings are on disk and its graphics-card share is released."""
        out = self.public()
        if out["state"] in (DONE, FAILED) and not self.settled:
            out["state"] = RUNNING
        return out


class GpuQueue:
    def __init__(self, lock_dir: Path, persist: Callable[[Job], None] | None = None,
                 lock_poll_s: float = 1.0, budget_mb: int = DEFAULT_BUDGET_MB,
                 make_room: Callable[[], None] | None = None) -> None:
        self.lock_dir = lock_dir
        self.persist = persist
        self.lock_poll_s = lock_poll_s
        self.budget_mb = budget_mb
        self.make_room = make_room  # frees an idle model when only live memory is short
        self.jobs: dict[str, Job] = {}
        self._line: list[Job] = []  # card jobs not yet admitted, in press order
        self._counter = 0
        self._mu = threading.Condition()
        self._save_mu = threading.Lock()
        self._stop = threading.Event()

    def submit(self, asset_id: str, step: str, run: Callable[[Job], dict | None],
               need: str | int | None = None) -> Job:
        """`need` is a job type from gpu_lock.VRAM_MB (e.g. "generate:hi3dgen"), a number of
        MB, or None for the step name's entry (the whole card if the table has none)."""
        mb = need if isinstance(need, int) else vram_need(need or step)
        with self._mu:
            self._counter += 1
            job = Job(f"j{self._counter}-{int(time.time())}", asset_id, step, run, vram_mb=mb)
            job.persist = self._persist
            self.jobs[job.id] = job
            if mb != 0:
                self._line.append(job)
        job.save()
        threading.Thread(target=self._run_one, args=(job,), daemon=True,
                         name=f"job-{job.id}").start()
        return job

    def ahead_of(self, job: Job) -> int:
        """How many card jobs are in front of this one, running or waiting (0 = it is running,
        next, or a CPU job that never waits)."""
        with self._mu:
            if job not in self._line:
                return 0
            return sum(1 for j in self.jobs.values()
                       if j.vram_mb != 0 and not j.settled and j.created <= job.created
                       and j is not job and (j not in self._line
                                             or self._line.index(j) < self._line.index(job)))

    def wait(self, job_id: str, timeout: float = 30.0) -> Job:
        job = self.jobs[job_id]
        end = time.time() + timeout
        while not job.settled and time.time() < end:
            time.sleep(0.02)
        return job

    def shutdown(self) -> None:
        self._stop.set()
        with self._mu:
            self._mu.notify_all()

    def _persist(self, job: Job) -> None:
        if self.persist:
            with self._save_mu:  # jobs run on their own threads; the store writes one at a time
                self.persist(job)

    def _admitted(self, job: Job) -> None:
        with self._mu:
            if job in self._line:
                self._line.remove(job)
            self._mu.notify_all()

    def _run_one(self, job: Job) -> None:
        def on_wait(owner: str) -> None:
            if job.state != WAITING:
                job.state = WAITING
                job.message = f"Waiting for the graphics card ({owner} is using it)"
                job.save()

        end, words = FAILED, "Something went wrong. Press Redo to try again."
        try:
            with self._mu:  # card jobs start in press order
                while job in self._line and self._line[0] is not job:
                    if self._stop.is_set():
                        raise InterruptedError("stopped while waiting for the graphics card")
                    self._mu.wait(0.5)
            with gpu_lock(self.lock_dir, f"asset-forge:{job.asset_id}:{job.step}",
                          self.lock_poll_s, on_wait, self._stop.is_set, vram_mb=job.vram_mb,
                          budget_mb=self.budget_mb, make_room=self.make_room):
                self._admitted(job)
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
            # Order matters (flaky batch test): the card share is released and `finished` is
            # set before the state flips; the save then writes the end state and the step's
            # timing; only then is the job settled, which is when the page sees it end.
            self._admitted(job)
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
