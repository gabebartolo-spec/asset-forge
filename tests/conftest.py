"""Shared fixtures for the app tests. Generation is always a fake: no GPU in CI."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from asset_forge.config import Settings
from asset_forge.generators import Generator, GeneratorError, GenResult, Registry


def make_png(plain_background: bool = True) -> bytes:
    """A red blob on a white background (or already cut out when plain_background is False)."""
    bg = (255, 255, 255, 255) if plain_background else (0, 0, 0, 0)
    img = Image.new("RGBA", (200, 200), bg)
    ImageDraw.Draw(img).ellipse((50, 40, 150, 170), fill=(200, 30, 30, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class FakeGenerator(Generator):
    label = "Fake"
    blurb = "fake"
    typical_time = "about 1 second"
    vram = "uses about 1 GB of video memory (VRAM)"

    def __init__(self, gen_id: str, name: str, fail: bool = False, sleep: float = 0.0,
                 log: list | None = None) -> None:
        self.id, self.name, self.fail, self.sleep = gen_id, name, fail, sleep
        self.log = log if log is not None else []
        self.seeds: list[int] = []

    def run(self, image: Path, out_dir: Path, seed: int, progress) -> GenResult:
        self.log.append(("start", self.id))
        progress("Building the 3D shape...")
        time.sleep(self.sleep)
        self.seeds.append(seed)
        self.log.append(("end", self.id))
        if self.fail:
            raise GeneratorError(f"{self.name} could not make a model. Press Redo.")
        glb = out_dir / "raw.glb"
        glb.write_bytes(b"glTF-fake")
        return GenResult(glb, 1.5, 2.0, {"faces": 12})


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        repo=Path(__file__).resolve().parents[1], models_dir=tmp_path / "models",
        library_dir=tmp_path / "library",
    )


@pytest.fixture
def fake_registry() -> Registry:
    return Registry([FakeGenerator("hi3dgen", "Hi3DGen"), FakeGenerator("triposg", "TripoSG")])


GOOD_REPORT = {
    "triangles": 7600, "triangle_budget": 8000, "raw_triangles": 310000, "materials": 1,
    "texture": {"width": 1024, "height": 1024, "max_px": 1024}, "height_m": 1.8,
    "silhouette": {"threshold": 0.08, "front": 0.02, "side": 0.03, "top": 0.04},
}


def fake_cleaner(report: dict | None = None, code: int = 0, log: list | None = None):
    """A stand-in for the Blender run: writes clean.glb and report.json where clean.py would."""
    def run(cmd: list[str]) -> tuple[int, str]:
        if log is not None:
            log.append(cmd)
        out = Path(cmd[cmd.index("--") + 2])
        out.mkdir(parents=True, exist_ok=True)
        if code == 0:
            (out / "clean.glb").write_bytes(b"glTF-clean")
            animal = cmd[cmd.index("--type") + 1] == "animal"  # the animal budget is tighter
            good = {**GOOD_REPORT, "triangles": 1800, "texture": {"width": 512, "height": 512}
                    } if animal else GOOD_REPORT
            (out / "report.json").write_text(json.dumps(report or good))
        return code, "log"
    return run
