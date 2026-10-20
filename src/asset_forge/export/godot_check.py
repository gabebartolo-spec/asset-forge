"""Headless Godot import check: does this .glb load with no errors or warnings?"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3] / "godot" / "import_check"
_BAD_LINE = re.compile(
    r"(^|\s)(ERROR|WARNING|SCRIPT ERROR|USER ERROR|USER WARNING)|IMPORT_CHECK_FAIL|RIG_CHECK_FAIL"
)
LOOP_NONE, LOOP_LINEAR = 0, 1  # Godot's Animation.LoopMode


@dataclass
class GodotResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    summary: str = ""


def godot_exe(config_path: Path | None = None) -> Path | None:
    """The Godot console exe from config.local.toml, or None when it is not set."""
    cfg = config_path or Path(__file__).resolve().parents[3] / "config.local.toml"
    if not cfg.is_file():
        return None
    exe = tomllib.loads(cfg.read_text(encoding="utf-8")).get("godot", {}).get("exe", "")
    return Path(exe) if exe else None


def check_glb(glb: Path, exe: Path | None = None, timeout: float = 120) -> GodotResult:
    """Run the import check. Always headless, with an isolated APPDATA."""
    return _run(glb, exe, timeout, "check.gd", [], "IMPORT_CHECK_OK")


def check_rig(glb: Path, exe: Path | None = None, humanoid: bool = False,
              timeout: float = 120) -> GodotResult:
    """Import check for a rigged .glb: one skeleton, a skinned mesh, at most 4 bone weights per
    vertex, at most 64 bones; for a humanoid also that SkeletonProfileHumanoid maps it."""
    return _run(glb, exe, timeout, "check_skeleton.gd", ["humanoid"] if humanoid else [],
                "RIG_CHECK_OK")


def loop_sidecar(looping) -> str:
    """The Godot import settings file (`<name>.glb.import`) that makes the named clips loop.
    Godot reads it when the .glb is imported into a project; every other setting keeps its
    default, and Godot fills in the rest of the file on the first import."""
    anims = ",\n".join(f'"{n}": {{\n"settings/loop_mode": {LOOP_LINEAR}\n}}' for n in looping)
    return ('[remap]\n\nimporter="scene"\nimporter_version=1\n\n[params]\n\n'
            f'_subresources={{\n"animations": {{\n{anims}\n}}\n}}\n')


def write_loop_sidecar(glb: Path, looping) -> Path:
    side = Path(glb).with_name(Path(glb).name + ".import")
    side.write_text(loop_sidecar(looping), encoding="utf-8", newline="\n")
    return side


def check_import(glb: Path, loops: dict[str, int], exe: Path | None = None,
                 timeout: float = 300) -> GodotResult:
    """Import the .glb as a game project would (the editor import, which reads the .glb.import
    sidecar beside it), then check every clip in `loops` is there with that loop mode.
    Headless, in a scratch project with an isolated APPDATA."""
    exe = exe or godot_exe()
    if exe is None or not Path(exe).is_file():
        return GodotResult(False, ["Godot is not set up: put its console exe in config.local.toml"])
    glb = Path(glb).resolve()
    if not glb.is_file():
        return GodotResult(False, [f"the file {glb.name} does not exist"])
    out, rc = "", 0
    with tempfile.TemporaryDirectory(prefix="forge_godot_import_") as scratch:
        proj = Path(scratch) / "project"
        proj.mkdir()
        for f in ("project.godot", "check_import.gd"):
            shutil.copy2(PROJECT_DIR / f, proj / f)
        shutil.copy2(glb, proj / "model.glb")
        side = glb.with_name(glb.name + ".import")
        if side.is_file():
            shutil.copy2(side, proj / "model.glb.import")
        env = {**os.environ, "APPDATA": scratch, "LOCALAPPDATA": scratch}
        steps = [["--import"],
                 ["--script", "res://check_import.gd", "--", "res://model.glb",
                  *(f"{k}={v}" for k, v in loops.items())]]
        for extra in steps:
            try:
                proc = subprocess.run([str(exe), "--headless", "--path", str(proj), *extra],
                                      env=env, capture_output=True, text=True,
                                      timeout=timeout, cwd=scratch)
            except subprocess.TimeoutExpired:
                return GodotResult(False, ["Godot took too long to import the file"])
            out += proc.stdout + "\n" + proc.stderr + "\n"
            rc = proc.returncode
            if rc != 0:
                break
    lines = out.splitlines()
    problems = [ln.strip() for ln in lines if _BAD_LINE.search(ln)]
    if rc != 0 and not problems:
        problems = [f"Godot exited with code {rc}"]
    summary = next((ln for ln in lines if ln.startswith("LOOP_CHECK_OK")), "")
    if not summary and not problems:
        problems = ["Godot did not confirm the import"]
    return GodotResult(not problems, problems, summary)


def _run(glb: Path, exe: Path | None, timeout: float, script: str, extra: list[str],
         ok_prefix: str) -> GodotResult:
    exe = exe or godot_exe()
    if exe is None or not Path(exe).is_file():
        return GodotResult(False, ["Godot is not set up: put its console exe in config.local.toml"])
    glb = Path(glb).resolve()
    if not glb.is_file():
        return GodotResult(False, [f"the file {glb.name} does not exist"])
    with tempfile.TemporaryDirectory(prefix="forge_godot_") as scratch:
        env = {**os.environ, "APPDATA": scratch, "LOCALAPPDATA": scratch}
        cmd = [str(exe), "--headless", "--path", str(PROJECT_DIR), "--script", script,
               "--", str(glb), *extra]
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  timeout=timeout, cwd=scratch)
        except subprocess.TimeoutExpired:
            return GodotResult(False, ["Godot took too long to load the file"])
    lines = (proc.stdout + "\n" + proc.stderr).splitlines()
    problems = [ln.strip() for ln in lines if _BAD_LINE.search(ln)]
    if proc.returncode != 0 and not problems:
        problems = [f"Godot exited with code {proc.returncode}"]
    summary = next((ln for ln in lines if ln.startswith(ok_prefix)), "")
    if not summary and not problems:
        problems = ["Godot did not confirm the import"]
    return GodotResult(not problems, problems, summary)
