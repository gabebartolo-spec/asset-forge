"""The end-to-end runner's step logic and summary, with the app's API faked (no server, no GPU)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "e2e"))

import run_e2e as e2e  # noqa: E402


class FakeApi(e2e.Api):
    """Answers the page's calls from a table; any POST listed in `refuse` fails with that
    (status, detail), and any step listed in `fail_jobs` ends as a failed job."""

    def __init__(self, refuse=None, fail_jobs=None, clean_passed=True):
        super().__init__("http://fake", poll_s=0, sleep=lambda s: None)
        self.refuse = refuse or {}
        self.fail_jobs = fail_jobs or {}
        self.clean_passed = clean_passed
        self.calls = []
        self.jobs = {}

    def _job(self, step, result):
        jid = f"j{len(self.jobs)}"
        if step in self.fail_jobs:
            job = {"id": jid, "state": "failed", "error": self.fail_jobs[step], "elapsed_s": 2.0}
        else:
            job = {"id": jid, "state": "done", "elapsed_s": 9.0, "result": result}
        self.jobs[jid] = job
        return {"id": jid, "state": "queued"}

    def get(self, path):
        self.calls.append(("GET", path))
        if path.endswith("/skeleton/limbs"):
            return {"spine": [[0, 0, 0], [0, 0, 1]], "counts": {"legs": 8},
                    "limbs": [{"kind": "leg", "joints": [[0, 0, 0], [1, 0, 0]], "side": "left"}]}
        return self.jobs[path.rsplit("/", 1)[1]]

    def upload(self, path, image, fields):
        self.calls.append(("UPLOAD", path, fields["type"]))
        return {"id": "a1", "type": fields["type"]}

    def post(self, path, body=None):
        self.calls.append(("POST", path))
        stepname = path.rsplit("/", 1)[1]
        if stepname in self.refuse:
            raise e2e.ApiError(*self.refuse[stepname])
        results = {
            "generate": {"total_s": 60.0, "gpu_peak_gb": 7.5},
            "clean": {"passed": self.clean_passed, "triangles": 7900, "triangle_budget": 8000,
                      "texture": {"width": 1024, "height": 1024}, "materials": 1,
                      "problems": [] if self.clean_passed else ["Too many triangles."],
                      "all_problems": [] if self.clean_passed else ["Too many triangles."],
                      "total_s": 80.0},
            "skeleton": {"bones": 22, "max_influences": 4, "template": "humanoid",
                         "problems": [], "total_s": 30.0},
            "animate": {"clips": [{"name": c} for c in e2e.CLIPS], "checks": {"slide_cm": 0.4},
                        "total_s": 40.0},
            "export": {"measured": {"triangles": 7900, "bones": 22, "influences": 4},
                       "godot_rig": "ok", "godot_import": "ok", "folder": "exports/a1"},
        }
        return self._job(stepname, results[stepname])


HUMANOID = {"id": "humanoid", "type": "humanoid", "text": "a knight"}
SPIDER = {"id": "spider", "type": "monster", "text": "a spider"}


def test_humanoid_runs_every_step_and_records_gates(tmp_path):
    rec = e2e.run_model(FakeApi(), HUMANOID, "hi3dgen", can_draw=False, refs_dir=tmp_path)
    assert [rec["steps"][s]["state"] for s in e2e.STEPS] == ["pass"] * 6
    assert rec["gates"]["triangles"] == 7900 and rec["gates"]["bones"] == 22
    assert rec["gates"]["max_influences"] == 4
    assert rec["godot"]["import"] == "ok"
    assert rec["steps"]["generate"]["seconds"] == 60.0  # the job's own total_s, not elapsed
    assert e2e.model_total_s(rec) == 219.0  # export reports no total_s: its elapsed 9 s counts
    assert e2e.furthest(rec) == "export"


def test_monster_refused_at_skeleton_is_refused_not_fail(tmp_path):
    api = FakeApi(refuse={"skeleton": (400, "Monsters get their skeleton later.")})
    rec = e2e.run_model(api, SPIDER, "triposg", can_draw=False, refs_dir=tmp_path)
    states = [rec["steps"][s]["state"] for s in e2e.STEPS]
    assert states == ["pass", "pass", "pass", "refused", "skipped", "skipped"]
    assert ("POST", "/api/assets/a1/animate") not in api.calls
    s = e2e.summarise([rec])
    assert s["end_to_end"] == 0 and s["failures"] == []
    assert s["refusals"][0]["step"] == "skeleton"


def test_monster_builds_its_skeleton_from_the_proposed_limbs(tmp_path):
    class BodyApi(FakeApi):
        def post(self, path, body=None):
            if path.endswith("/skeleton"):
                self.sent = body
            return super().post(path, body)

    api = BodyApi(refuse={"animate": (400, "Monsters get their animations later.")})
    rec = e2e.run_model(api, SPIDER, "hi3dgen", can_draw=False, refs_dir=tmp_path)
    assert ("GET", "/api/assets/a1/skeleton/limbs") in api.calls
    assert api.sent == {"spine": [[0, 0, 0], [0, 0, 1]],
                        "limbs": [{"kind": "leg", "joints": [[0, 0, 0], [1, 0, 0]]}]}
    assert rec["gates"]["limbs_proposed"] == {"legs": 8}
    assert rec["steps"]["skeleton"]["state"] == "pass"
    assert rec["steps"]["animate"]["state"] == "refused"


def test_clean_that_breaks_a_limit_counts_as_fail_and_stops(tmp_path):
    rec = e2e.run_model(FakeApi(clean_passed=False), HUMANOID, "hi3dgen", False, tmp_path)
    assert rec["steps"]["clean"]["state"] == "fail"
    assert "Too many triangles" in rec["steps"]["clean"]["error"]
    assert rec["steps"]["skeleton"]["state"] == "skipped"


def test_failed_job_keeps_the_apps_plain_words(tmp_path):
    api = FakeApi(fail_jobs={"export": "This model cannot be exported yet: too many bones."})
    rec = e2e.run_model(api, HUMANOID, "hi3dgen", False, tmp_path)
    assert rec["steps"]["export"]["state"] == "fail"
    assert rec["godot"] == {"refused": "This model cannot be exported yet: too many bones."}


def test_summary_and_markdown_count_each_step(tmp_path):
    ok = e2e.run_model(FakeApi(), HUMANOID, "hi3dgen", False, tmp_path)
    bad = e2e.run_model(FakeApi(fail_jobs={"generate": "The 3D maker ran out of memory."}),
                        HUMANOID, "triposg", False, tmp_path)
    s = e2e.summarise([ok, bad])
    assert s["models"] == 2 and s["end_to_end"] == 1
    assert s["per_step"]["generate"] == {"pass": 1, "fail": 1, "refused": 0, "skipped": 0}
    assert s["per_step"]["export"]["skipped"] == 1
    assert s["failures"] == [{"model": "triposg_humanoid", "step": "generate",
                              "error": "The 3D maker ran out of memory."}]
    md = e2e.render_md({"run": "t", "url": "u", "summary": s, "models": [ok, bad]})
    assert "| hi3dgen_humanoid | pass | pass | pass | pass | pass | pass | 219 | 7900 | 22 |" in md
    assert "triposg_humanoid at generate: The 3D maker ran out of memory." in md


def test_draw_path_used_when_the_app_can_draw(tmp_path):
    class DrawApi(FakeApi):
        def post(self, path, body=None):
            if path == "/api/assets/from-text":
                self.calls.append(("POST", path))
                return {"id": "a1"}
            if path.endswith("/draw"):
                self.calls.append(("POST", path))
                return self._job("draw", {"seed": 1, "draw_s": 20.0})
            return super().post(path, body)

    api = DrawApi()
    rec = e2e.run_model(api, HUMANOID, "hi3dgen", can_draw=True, refs_dir=tmp_path)
    assert rec["steps"]["reference"]["state"] == "pass"
    assert rec["steps"]["reference"]["mode"] == "drawn from the words"
    assert not any(c[0] == "UPLOAD" for c in api.calls)
