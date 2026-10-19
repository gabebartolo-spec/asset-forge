import threading
import time

from asset_forge.generators import GeneratorError
from asset_forge.jobqueue import DONE, FAILED, RUNNING, WAITING, GpuQueue


def test_jobs_run_one_at_a_time_in_press_order(tmp_path):
    q = GpuQueue(tmp_path / "gpu.lock", lock_poll_s=0.01)
    active, peak, order = 0, 0, []
    mu = threading.Lock()

    def work(name):
        def run(job):
            nonlocal active, peak
            with mu:
                active += 1
                peak = max(peak, active)
                order.append(name)
            time.sleep(0.05)
            with mu:
                active -= 1
            return {"name": name}
        return run

    jobs = [q.submit("a", "generate", work(n)) for n in "abcd"]
    for j in jobs:
        q.wait(j.id, 10)
    q.shutdown()
    assert peak == 1
    assert order == list("abcd")
    assert all(j.state == DONE for j in jobs)
    assert jobs[2].result == {"name": "c"}


def test_job_waits_while_another_program_holds_the_gpu_lock(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.mkdir()
    (lock / "owner.txt").write_text("bakeoff:triposg pid=1\n")
    q = GpuQueue(lock, lock_poll_s=0.01)
    job = q.submit("a", "generate", lambda j: {"ok": True})
    time.sleep(0.3)
    assert job.state == WAITING
    assert "bakeoff:triposg" in job.message and "graphics card" in job.message
    (lock / "owner.txt").unlink()
    lock.rmdir()
    q.wait(job.id, 10)
    q.shutdown()
    assert job.state == DONE
    assert not lock.exists(), "the lock is released after the job"


def test_the_lock_is_held_while_running_and_released_on_failure(tmp_path):
    lock = tmp_path / "gpu.lock"
    q = GpuQueue(lock, lock_poll_s=0.01)
    seen = {}

    def boom(job):
        seen["held"] = lock.exists()
        seen["state"] = job.state
        raise GeneratorError("Hi3DGen could not make a model. Press Redo.")

    job = q.submit("a", "generate", boom)
    q.wait(job.id, 10)
    q.shutdown()
    assert seen == {"held": True, "state": RUNNING}
    assert job.state == FAILED and job.error == "Hi3DGen could not make a model. Press Redo."
    assert not lock.exists()


def test_unexpected_errors_get_a_plain_message_not_a_traceback(tmp_path):
    q = GpuQueue(tmp_path / "gpu.lock", lock_poll_s=0.01)

    def boom(job):
        raise KeyError("secret internal detail")

    job = q.submit("a", "generate", boom)
    q.wait(job.id, 10)
    q.shutdown()
    assert job.state == FAILED
    assert "secret" not in job.error and "Redo" in job.error


def test_status_is_persisted_at_each_change(tmp_path):
    seen = []
    q = GpuQueue(tmp_path / "gpu.lock", persist=lambda j: seen.append(j.state), lock_poll_s=0.01)
    job = q.submit("a", "generate", lambda j: {})
    q.wait(job.id, 10)
    q.shutdown()
    assert seen[0] == "queued" and seen[-1] == "done" and "running" in seen
