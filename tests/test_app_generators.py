import json
import sys
from pathlib import Path

import pytest
from conftest import make_png

from asset_forge import generators
from asset_forge.generators import GeneratorError, Hi3DGen, TripoSG

FAKE_ADAPTER = """
import argparse, json, sys, time
from pathlib import Path
ap = argparse.ArgumentParser()
for k in ("--inputs", "--out", "--src", "--seed"):
    ap.add_argument(k)
a = ap.parse_args()
out = Path(a.out)
(out / "model.glb").write_bytes(b"glTF" + a.seed.encode())
print("BEGIN model", flush=True)
time.sleep(0.7)
print("END model", flush=True)
items = [{"id": "model", "mesh": str(out / "model.glb"), "gen_s": 3.25, "faces": 99,
          "torch_peak_gb": 4.0, "error": None}]
if "fail" in a.src:
    items = [{"id": "model", "mesh": None, "gen_s": 1.0, "error": "OOM"}]
(out / "results.json").write_text(json.dumps(
    {"load_s": 2.0, "settings": {"s": 1}, "items": items}))
sys.exit(1 if "crash" in a.src else 0)
"""


class Fake(Hi3DGen):
    def __init__(self, settings, adapter, src):
        super().__init__(settings)
        self._adapter, self._src = adapter, src

    def paths(self):
        return Path(sys.executable), self._adapter, self._src


@pytest.fixture
def adapter(tmp_path):
    p = tmp_path / "fake_adapter.py"
    p.write_text(FAKE_ADAPTER)
    return p


@pytest.fixture(autouse=True)
def no_gpu(monkeypatch):
    mem = iter([1000, 3048, 3048] + [3048] * 1000)
    monkeypatch.setattr(generators, "gpu_used_mib", lambda: next(mem))


def run(settings, adapter, tmp_path, src_name="ok"):
    src = tmp_path / src_name
    src.mkdir(exist_ok=True)
    img = tmp_path / "in.png"
    img.write_bytes(make_png())
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    msgs = []
    res = Fake(settings, adapter, src).run(img, out, 5, msgs.append)
    return res, out, msgs


def test_runs_the_adapter_in_a_subprocess_and_collects_the_mesh(settings, adapter, tmp_path):
    res, out, msgs = run(settings, adapter, tmp_path)
    assert res.mesh == out / "raw.glb" and res.mesh.read_bytes() == b"glTF5"
    assert res.gen_s == 3.25 and res.details["faces"] == 99
    assert res.gpu_peak_gb == 2.0
    assert "Building the 3D shape..." in msgs
    assert not (out / "_work").exists() and (out / "generator.log").exists()


@pytest.mark.parametrize("name", ["fail_item", "crash"])
def test_adapter_failure_is_plain_words(settings, adapter, tmp_path, name):
    with pytest.raises(GeneratorError, match="Press Redo"):
        run(settings, adapter, tmp_path, name)


def test_missing_environment_names_the_fix(settings, tmp_path):
    img = tmp_path / "in.png"
    img.write_bytes(make_png())
    with pytest.raises(GeneratorError, match="not set up on this PC yet. Pick the other"):
        TripoSG(settings).run(img, tmp_path, 1, lambda m: None)


def test_command_uses_the_models_env_and_the_bakeoff_adapter(settings, tmp_path):
    cmd = Hi3DGen(settings).command(tmp_path / "in", tmp_path / "out", 9)
    assert Path(cmd[0]).parts[-4:] == ("envs", "hi3dgen", "Scripts", "python.exe")
    assert cmd[1].replace("\\", "/").endswith("tools/bakeoff/adapters/hi3dgen.py")
    assert cmd[cmd.index("--seed") + 1] == "9"
    assert all(isinstance(c, str) for c in cmd)
    assert json.dumps(cmd)
