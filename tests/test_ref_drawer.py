"""SdxlReferenceDrawer: prompts per type and the fallback when the weights are missing.
The SDXL process is replaced by a fake runner; no GPU here."""

from __future__ import annotations

import pytest

from asset_forge.config import Settings
from asset_forge.draw import (
    DrawError,
    SdxlReferenceDrawer,
    UnavailableDrawer,
    default_drawer,
)

PNG = b"\x89PNG fake"


class Runner:
    def __init__(self, out=PNG, fail=""):
        self.jobs, self.out, self.fail = [], out, fail

    def __call__(self, job, progress):
        self.jobs.append(job)
        if self.fail:
            raise DrawError(self.fail)
        return self.out


def drawer(runner):
    return SdxlReferenceDrawer(runner=runner)


@pytest.mark.parametrize("kind,needle", [
    ("humanoid", "A-pose"),
    ("monster", "three-quarter"),
    ("animal", "side view"),
])
def test_prompt_per_type(kind, needle):
    r = Runner()
    out = drawer(r).draw("a knight", kind, 7, lambda m: None)
    assert out == PNG
    job = r.jobs[0]
    assert job["prompt"].startswith("a knight")
    assert needle in job["prompt"]
    assert "plain flat white background" in job["prompt"]
    assert "no text" in job["prompt"]
    assert job["seed"] == 7
    assert "cropped" in job["negative"]


def test_types_differ():
    r = Runner()
    d = drawer(r)
    for kind in ("humanoid", "monster", "animal"):
        d.draw("x", kind, 1, lambda m: None)
    assert len({j["prompt"] for j in r.jobs}) == 3


def test_unknown_type_is_plain_error():
    with pytest.raises(DrawError):
        drawer(Runner()).draw("x", "robot", 1, lambda m: None)


def test_runner_error_passes_through():
    with pytest.raises(DrawError, match="card is busy"):
        drawer(Runner(fail="card is busy")).draw("x", "animal", 1, lambda m: None)


def test_default_drawer_unavailable_without_weights(tmp_path):
    d = default_drawer(Settings(models_dir=tmp_path))
    assert isinstance(d, UnavailableDrawer) and not d.available and d.note


def test_default_drawer_available_with_weights(tmp_path):
    py = tmp_path / "envs" / "sdxl" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("")
    snap = tmp_path / "hf" / "hub" / "models--stabilityai--stable-diffusion-xl-base-1.0"
    (snap / "snapshots" / "abc").mkdir(parents=True)
    (snap / "snapshots" / "abc" / "model_index.json").write_text("{}")
    d = default_drawer(Settings(models_dir=tmp_path))
    assert isinstance(d, SdxlReferenceDrawer) and d.available
