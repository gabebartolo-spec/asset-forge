"""Step 2 behind the app's one API call: run `blender/clean.py` headless on the raw model, read
its report.json and turn it into a verdict in plain words (design 5.2, section 6).

    clean_model(...)  ->  result dict (also written to library/<id>/clean/result.json)

The Blender run is injectable (`runner`) so tests and CI never start Blender. A model that
breaks a gate still comes back as a result (`passed: False`, the broken limits in `problems`),
so the page can show it and offer Redo; only a run that produced no report raises CleanFailed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .config import Settings
from .generators import GeneratorError
from .steps import clean_command

# The names clean.py gives its outputs; removed before a redo so an old model never lingers.
OUTPUTS = ("clean.glb", "clean.blend", "texture.png", "report.json", "result.json")
TIMEOUT_S = 1200

Runner = Callable[[list[str]], tuple[int, str]]  # command -> (exit code, text output)


class CleanFailed(GeneratorError):
    """The clean-up did not run to the end; the message is plain words."""


def blender_runner(blender_exe: str) -> Runner:
    def run(cmd: list[str]) -> tuple[int, str]:
        if not blender_exe or not Path(blender_exe).is_file():
            raise CleanFailed("Blender is not set up: put its path in config.local.toml.")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise CleanFailed("Cleaning up took too long. Press Redo.") from None
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    return run


def colour_problems(report: dict) -> list[str]:
    """Measured colour checks (animals) that failed, as sentences."""
    gates = (report.get("colour_route") or {}).get("region_gates") or {}
    if gates.get("passed", True):
        return []
    return [f"The colours are off at '{g['gate']}': {g['value']} where the limit is {g['limit']}."
            for g in gates.get("gates", []) if not g.get("ok", True)]


def verdict(report: dict, asset_type: str) -> list[str]:
    from .gates import check  # owned by the Clean step (PR #9)

    return check(report, asset_type) + colour_problems(report)


def summary(report: dict, asset_type: str) -> dict:
    tex = report.get("texture") or {}
    problems = verdict(report, asset_type)
    return {
        "passed": not problems, "problems": problems,
        "triangles": report.get("triangles"), "triangle_budget": report.get("triangle_budget"),
        "raw_triangles": report.get("raw_triangles"),
        "texture": {"width": tex.get("width"), "height": tex.get("height")},
        "materials": report.get("materials"), "height_m": report.get("height_m"),
        "silhouette": report.get("silhouette"),
    }


def clean_model(settings: Settings, asset: dict, gen_dir: Path, out_dir: Path,
                runner: Runner, progress: Callable[[str], None]) -> dict:
    """Run the clean-up for one asset. `asset` is store.get_asset()."""
    gen = (asset.get("steps", {}).get("generate") or {})
    mesh = (gen.get("result") or {}).get("mesh")
    raw = gen_dir / mesh if mesh else None
    ref = gen_dir / "input.png"
    if not raw or not raw.is_file() or not ref.is_file():
        raise CleanFailed("Make the 3D model first (step 1), then clean it up.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:
        (out_dir / name).unlink(missing_ok=True)
    for sub in ("before", "after"):
        shutil.rmtree(out_dir / sub, ignore_errors=True)
    cmd = clean_command(settings.blender_exe, settings.repo, raw, out_dir, asset["type"], ref,
                        generator=(gen.get("result") or {}).get("generator"))
    progress("Rebuilding the model...")
    t0 = time.time()
    code, _log = runner(cmd)
    report_path = out_dir / "report.json"
    if code != 0 or not report_path.is_file() or not (out_dir / "clean.glb").is_file():
        raise CleanFailed("The clean-up could not finish on this model. Press Redo; if it "
                          "happens again, go back and make the model again.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    res = summary(report, asset["type"])
    res["total_s"] = round(time.time() - t0, 1)
    return res
