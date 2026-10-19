"""Headless Godot import check: does this .glb load with no errors or warnings?"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3] / "godot" / "import_check"
_BAD_LINE = re.compile(
    r"(^|\s)(ERROR|WARNING|SCRIPT ERROR|USER ERROR|USER WARNING)|IMPORT_CHECK_FAIL"
)


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
    exe = exe or godot_exe()
    if exe is None or not Path(exe).is_file():
        return GodotResult(False, ["Godot is not set up: put its console exe in config.local.toml"])
    glb = Path(glb).resolve()
    if not glb.is_file():
        return GodotResult(False, [f"the file {glb.name} does not exist"])
    with tempfile.TemporaryDirectory(prefix="forge_godot_") as scratch:
        env = {**os.environ, "APPDATA": scratch, "LOCALAPPDATA": scratch}
        cmd = [str(exe), "--headless", "--path", str(PROJECT_DIR), "--script", "check.gd",
               "--", str(glb)]
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  timeout=timeout, cwd=scratch)
        except subprocess.TimeoutExpired:
            return GodotResult(False, ["Godot took too long to load the file"])
    lines = (proc.stdout + "\n" + proc.stderr).splitlines()
    problems = [ln.strip() for ln in lines if _BAD_LINE.search(ln)]
    if proc.returncode != 0 and not problems:
        problems = [f"Godot exited with code {proc.returncode}"]
    summary = next((ln for ln in lines if ln.startswith("IMPORT_CHECK_OK")), "")
    if not summary and not problems:
        problems = ["Godot did not confirm the import"]
    return GodotResult(not problems, problems, summary)
