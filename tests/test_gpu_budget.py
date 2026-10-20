"""The graphics-card budget (D-030): jobs that fit run together, a big one waits, CPU jobs
never wait, a dead holder is cleared, and old-style holders still have the whole card."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from asset_forge.gpu_lock import gpu_lock, lock_owner, vram_need
from asset_forge.jobqueue import DONE, RUNNING, WAITING, GpuQueue

REPO = Path(__file__).resolve().parents[1]


def _spans(q, jobs, hold=0.3):
    """Submit (step, need) jobs that each sleep `hold`; return {name: (start, end)}."""
    spans, mu = {}, threading.Lock()

    def work(name):
        def run(job):
            t0 = time.time()
            time.sleep(hold)
            with mu:
                spans[name] = (t0, time.time())
            return {}
        return run

    made = [q.submit("a", step, work(name), need=need) for name, step, need in jobs]
    for j in made:
        q.wait(j.id, 20)
    q.shutdown()
    assert all(j.state == DONE for j in made)
    return spans


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def test_two_small_jobs_run_together(tmp_path):
    q = GpuQueue(tmp_path / "gpu.lock", lock_poll_s=0.01, budget_mb=11000)
    s = _spans(q, [("x", "expand", "expand:qwen"), ("y", "generate", "generate:triposr")])
    assert _overlap(s["x"], s["y"]), "4200 + 5400 MB fit 11000 MB: both run at once"


def test_a_big_job_waits_for_room_and_keeps_its_place(tmp_path):
    q = GpuQueue(tmp_path / "gpu.lock", lock_poll_s=0.01, budget_mb=11000)
    s = _spans(q, [("small", "generate", "generate:hi3dgen"),
                   ("big", "generate", "draw:sdxl"),
                   ("later", "generate", "generate:triposr")])
    assert not _overlap(s["small"], s["big"]), "6800 + 10800 MB do not fit"
    assert s["big"][0] >= s["small"][1]
    assert s["later"][0] >= s["big"][0], "a later card job never jumps a waiting one"


def test_cpu_jobs_never_wait_even_behind_a_whole_card_holder(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.mkdir()
    (lock / "owner.txt").write_text("bakeoff:triposg pid=1\n")  # an old-style holder
    q = GpuQueue(lock, lock_poll_s=0.01)
    gpu = q.submit("a", "generate", lambda j: {}, need="generate:hi3dgen")
    cpu = q.submit("a", "skeleton", lambda j: {"rigged": True})  # table: 0 MB
    q.wait(cpu.id, 5)
    assert cpu.state == DONE and cpu.vram_mb == 0
    end = time.time() + 5
    while gpu.state != WAITING and time.time() < end:
        time.sleep(0.01)
    assert gpu.state == WAITING and "bakeoff:triposg" in gpu.message
    (lock / "owner.txt").unlink()
    lock.rmdir()
    q.wait(gpu.id, 10)
    q.shutdown()
    assert gpu.state == DONE and not lock.exists()


def test_a_dead_holder_is_cleared(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.mkdir()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (lock / f"holder-{dead.pid}-dead.json").write_text(json.dumps(
        {"owner": "crashed", "pid": dead.pid, "vram_mb": 11000, "exclusive": True}))
    with gpu_lock(lock, "me", vram_mb=6800, poll_s=0.01, card=lambda: None):
        assert [f.name for f in lock.glob("holder-*")] != [f"holder-{dead.pid}-dead.json"]
        assert "crashed" not in lock_owner(lock)
    assert not lock.exists()


def test_a_live_holder_blocks_by_budget_and_names_itself(tmp_path):
    lock = tmp_path / "gpu.lock"
    seen = []
    with gpu_lock(lock, "hi3dgen job", vram_mb=6800, poll_s=0.01, card=lambda: None):
        stop = threading.Event()

        def second():
            with gpu_lock(lock, "sdxl", vram_mb=10800, poll_s=0.01, on_wait=seen.append,
                          cancelled=stop.is_set, card=lambda: None):
                seen.append("entered")

        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.2)
        assert seen and seen[0] == "hi3dgen job" and "entered" not in seen
    t.join(5)
    assert seen[-1] == "entered"


def test_live_free_memory_is_respected_and_make_room_is_tried(tmp_path):
    lock = tmp_path / "gpu.lock"
    free = {"mb": 3000}  # a model left loaded outside the budget
    calls = []

    def make_room():
        calls.append(1)
        free["mb"] = 11000

    with gpu_lock(lock, "draw", vram_mb=10800, poll_s=0.01, make_room=make_room,
                  card=lambda: (free["mb"], 12282)):
        pass
    assert calls == [1]


def test_exclusive_holder_waits_for_everyone_and_blocks_everyone(tmp_path):
    lock = tmp_path / "gpu.lock"
    order = []
    with gpu_lock(lock, "small", vram_mb=1000, poll_s=0.01, card=lambda: None):
        def whole():
            with gpu_lock(lock, "whole", vram_mb=None, poll_s=0.01, card=lambda: None):
                order.append("whole")

        t = threading.Thread(target=whole)
        t.start()
        time.sleep(0.15)
        order.append("small done")
    t.join(5)
    assert order == ["small done", "whole"]


def test_the_table_knows_cpu_steps_and_unknown_types_take_the_whole_card():
    for step in ("clean", "skeleton", "animate", "measure", "sprite-post"):
        assert vram_need(step) == 0
    assert vram_need("generate:hi3dgen") == 6800 and vram_need("draw:sdxl") == 10800
    assert vram_need("generate:something-new") is None and vram_need(None) is None


def test_running_job_holds_an_entry_with_its_need(tmp_path):
    lock = tmp_path / "gpu.lock"
    q = GpuQueue(lock, lock_poll_s=0.01)
    seen = {}

    def run(job):
        seen["state"] = job.state
        seen["entries"] = [json.loads(f.read_text()) for f in lock.glob("holder-*.json")]
        return {}

    j = q.submit("a", "generate", run, need="generate:triposg")
    q.wait(j.id, 10)
    q.shutdown()
    assert seen["state"] == RUNNING
    assert [(e["vram_mb"], e["exclusive"]) for e in seen["entries"]] == [(6300, False)]
    assert not lock.exists()


def test_cli_vram_flag_and_old_default(tmp_path):
    env = {**__import__("os").environ, "FORGE_MODELS_DIR": str(tmp_path)}
    tool = REPO / "tools" / "bakeoff" / "gpu_lock.py"
    probe = ("import json,pathlib,os;"
             "print(json.dumps([json.loads(f.read_text()) for f in "
             "pathlib.Path(os.environ['FORGE_MODELS_DIR'],'gpu.lock').glob('holder-*.json')]))")
    out = subprocess.run([sys.executable, str(tool), "run", "t", "--vram", "1234", "--",
                          sys.executable, "-c", probe], env=env, capture_output=True, text=True,
                         timeout=60, check=True).stdout
    assert [(e["vram_mb"], e["exclusive"]) for e in json.loads(out)] == [(1234, False)]
    out = subprocess.run([sys.executable, str(tool), "run", "t", "--",
                          sys.executable, "-c", probe], env=env, capture_output=True, text=True,
                         timeout=60, check=True).stdout
    assert [e["exclusive"] for e in json.loads(out)] == [True]
    assert not (tmp_path / "gpu.lock").exists()


def test_every_worktree_layout_shares_the_main_checkouts_lock(tmp_path, monkeypatch):
    from asset_forge.gpu_lock import shared_models_dir

    monkeypatch.delenv("FORGE_MODELS_DIR", raising=False)
    main = tmp_path / "asset-forge"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    for wt in (main / ".claude" / "worktrees" / "confident", tmp_path / "asset-forge-wt" / "x"):
        wt.mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
        assert shared_models_dir(wt) == main / "models"
    assert shared_models_dir(main) == main / "models"
    monkeypatch.setenv("FORGE_MODELS_DIR", str(tmp_path / "elsewhere"))
    assert shared_models_dir(main) == tmp_path / "elsewhere"


def test_old_positional_callers_still_take_the_whole_card(tmp_path):
    """clean.py and pre-D-030 branches call gpu_lock(lock, owner, poll_s): poll_s must never
    be read as a VRAM need."""
    lock = tmp_path / "gpu.lock"
    with gpu_lock(lock, "clean multiview", 5.0):
        (entry,) = [json.loads(f.read_text()) for f in lock.glob("holder-*.json")]
        assert entry["exclusive"] is True
    assert vram_need("clean:multiview") == 11000


def test_clean_command_passes_the_lock_only_when_asked(tmp_path):
    from asset_forge.steps import clean_command

    args = ("blender", tmp_path, tmp_path / "raw.glb", tmp_path / "clean", "humanoid",
            tmp_path / "ref.png")
    assert "--gpu-lock" not in clean_command(*args)
    assert clean_command(*args, gpu_lock_dir=tmp_path / "gpu.lock")[-2:] == [
        "--gpu-lock", str(tmp_path / "gpu.lock")]
    assert vram_need("clean") == 0, "the Clean job itself never waits for the card"
