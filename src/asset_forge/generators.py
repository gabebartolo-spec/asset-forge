"""The generator interface and the two generators on the menu (D-018, D-019).

Each generator runs the bake-off adapter in its own environment (`models/envs/<name>`, D-012) as
a subprocess, so the app's Python never imports torch. The adapter contract is documented in
tools/bakeoff/run_candidate.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings


class GeneratorError(RuntimeError):
    """Message is shown to the person as it is: plain words plus the one click that fixes it."""


@dataclass
class GenResult:
    mesh: Path
    gen_s: float
    gpu_peak_gb: float | None = None
    details: dict = field(default_factory=dict)


class Generator(ABC):
    id: str
    name: str
    label: str  # two or three plain words next to the name
    blurb: str  # one plain line: what it is good at
    typical_time: str  # plain words, whole job from pressing Make to seeing the model
    vram: str  # plain words

    def menu_entry(self, selected: bool) -> dict:
        return {
            "id": self.id, "name": self.name, "label": self.label, "blurb": self.blurb,
            "typical_time": self.typical_time, "vram": self.vram, "selected": selected,
        }

    @abstractmethod
    def run(self, image: Path, out_dir: Path, seed: int,
            progress: Callable[[str], None]) -> GenResult:
        """Turn the cut-out image into `out_dir/raw.glb`. Raise GeneratorError on failure."""


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    return int(out.strip().splitlines()[0])


class _VramSampler(threading.Thread):
    """Peak graphics-card memory above where it was when the job started (as run_candidate)."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_flag = threading.Event()
        self.baseline: int | None = None
        self.peak = 0

    def run(self) -> None:
        while not self.stop_flag.is_set():
            try:
                used = gpu_used_mib()
                if self.baseline is None:
                    self.baseline = used
                self.peak = max(self.peak, used)
            except Exception:  # noqa: BLE001 - a missed sample is not fatal
                pass
            self.stop_flag.wait(0.25)

    def peak_gb(self) -> float | None:
        if self.baseline is None:
            return None
        return round((self.peak - self.baseline) / 1024, 2)


class SubprocessGenerator(Generator):
    """Runs tools/bakeoff/adapters/<id>.py with models/envs/<id>/Scripts/python.exe."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def paths(self) -> tuple[Path, Path, Path]:
        m = self.settings.models_dir
        py = m / "envs" / self.id / "Scripts" / "python.exe"
        adapter = self.settings.repo / "tools" / "bakeoff" / "adapters" / f"{self.id}.py"
        return py, adapter, m / "src" / self.id

    def command(self, inputs: Path, out: Path, seed: int) -> list[str]:
        py, adapter, src = self.paths()
        return [str(py), str(adapter), "--inputs", str(inputs), "--out", str(out),
                "--src", str(src), "--seed", str(seed)]

    def run(self, image: Path, out_dir: Path, seed: int,
            progress: Callable[[str], None]) -> GenResult:
        py, adapter, src = self.paths()
        if not (py.exists() and adapter.exists() and src.exists()):
            raise GeneratorError(
                f"{self.name} is not set up on this PC yet. Pick the other generator."
            )
        work = out_dir / "_work"
        if work.exists():
            shutil.rmtree(work)
        (work / "in").mkdir(parents=True)
        shutil.copyfile(image, work / "in" / "model.png")
        env = dict(os.environ)
        env.setdefault("HF_HOME", str(self.settings.models_dir / "hf"))
        env["PYTHONUNBUFFERED"] = "1"
        sampler = _VramSampler()
        sampler.start()
        log = (out_dir / "generator.log").open("w", encoding="utf-8")
        try:
            progress(f"Loading {self.name}...")
            proc = subprocess.Popen(
                self.command(work / "in", work, seed), env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            )
            assert proc.stdout
            for line in proc.stdout:
                log.write(line)
                log.flush()
                if line.startswith("BEGIN"):
                    progress("Building the 3D shape...")
            rc = proc.wait()
        finally:
            sampler.stop_flag.set()
            sampler.join(timeout=2)
            log.close()
        results = work / "results.json"
        item: dict = {}
        data: dict = {}
        if results.exists():
            data = json.loads(results.read_text(encoding="utf-8"))
            item = (data.get("items") or [{}])[0]
        mesh_name = item.get("mesh")
        mesh = work / Path(mesh_name).name if mesh_name else None
        if rc != 0 or item.get("error") or mesh is None or not mesh.exists():
            raise GeneratorError(
                f"{self.name} could not make a model from this picture. Press Redo to try "
                "again, or pick the other generator."
            )
        raw = out_dir / "raw.glb"
        shutil.move(str(mesh), raw)
        details = {"load_s": data.get("load_s"), "settings": data.get("settings"),
                   "faces": item.get("faces"), "torch_peak_gb": item.get("torch_peak_gb")}
        shutil.rmtree(work, ignore_errors=True)
        return GenResult(raw, float(item.get("gen_s") or 0.0), sampler.peak_gb(), details)


class Hi3DGen(SubprocessGenerator):
    id = "hi3dgen"
    name = "Hi3DGen"
    label = "Quick and clean"
    blurb = "Clean, crisp shapes. A good first try."
    typical_time = "1 to 2 minutes"  # measured 50-113 s through the app (fox.png)
    vram = "uses about 6 GB of video memory (VRAM)"


class TripoSG(SubprocessGenerator):
    id = "triposg"
    name = "TripoSG"
    label = "Most detail"
    blurb = "Follows your picture. Bigger file, slower in a game."
    typical_time = "2 to 5 minutes"  # fox.png: 92 s free GPU; 166-288 s shared
    vram = "uses about 5 GB of video memory (VRAM)"


GENERATOR_CLASSES: dict[str, type[SubprocessGenerator]] = {
    "hi3dgen": Hi3DGen, "triposg": TripoSG,
}


class Registry:
    """The menu: generators in the order from config; the first is preselected."""

    def __init__(self, generators: list[Generator]) -> None:
        if not generators:
            raise ValueError("at least one generator is needed")
        self.generators = generators

    @classmethod
    def from_settings(cls, settings: Settings) -> Registry:
        return cls([GENERATOR_CLASSES[g](settings) for g in settings.generator_order
                    if g in GENERATOR_CLASSES])

    def menu(self) -> list[dict]:
        return [g.menu_entry(i == 0) for i, g in enumerate(self.generators)]

    def get(self, generator_id: str) -> Generator:
        for g in self.generators:
            if g.id == generator_id:
                return g
        raise KeyError(generator_id)
