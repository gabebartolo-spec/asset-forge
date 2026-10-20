"""Step 4, Animate: six procedural clips from the Step 3 skeleton, checked, then exported.

The app shell calls:

    animate(rigged_blend, out_dir, blender_exe)  ->  AnimResult
        runs blender/animate.py headless; writes animated.glb (clips idle, walk, run, attack,
        hit, faint), animated.blend and clips.json; then re-reads the .glb and checks it
        (check.check_animated_glb: the clip names, loop seams, planted feet do not slide).

Export (the performance gate and the headless Godot check) is asset_forge.export.export_animated.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from asset_forge.animate.check import check_animated_glb
from asset_forge.animate.clips import CLIP_NAMES, LOOPING

REPO = Path(__file__).resolve().parents[3]
TEMPLATES_ANIMATED = ("humanoid", "four_legged", "bird")
NOT_YET = ("Monsters and creatures with six or more legs get their animations in a later "
           "version. People and four- or two-legged animals work today.")


class AnimFailed(Exception):
    """The clips were not made; the message says so in plain words."""


@dataclass
class AnimResult:
    out_dir: Path
    template: str
    clips: list[dict]
    seconds: float
    checks: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return {"template": self.template, "clips": self.clips, "seconds": self.seconds,
                "checks": self.checks, "notes": self.notes}


def animate_command(blender_exe: str, repo: Path, rigged_blend: Path, out_dir: Path,
                    previews: Path | None = None, size: int = 320) -> list[str]:
    cmd = [blender_exe, "-b", "--factory-startup", "-P", str(repo / "blender" / "animate.py"),
           "--", str(rigged_blend), str(out_dir)]
    if previews:
        cmd += ["--previews", str(previews), "--preview-size", str(size)]
    return cmd


def animate(rigged_blend: Path, out_dir: Path, blender_exe: str, asset_type: str = "humanoid",
            repo: Path = REPO, previews: Path | None = None, timeout: float = 900) -> AnimResult:
    """Run the Animate step. Raises AnimFailed (plain words) when it cannot finish."""
    rigged_blend, out_dir = Path(rigged_blend), Path(out_dir)
    if asset_type == "monster":
        raise AnimFailed(NOT_YET)
    if not rigged_blend.is_file():
        raise AnimFailed("There is no skeleton yet. Build the skeleton in step 3 first.")
    if not blender_exe or not Path(blender_exe).is_file():
        raise AnimFailed("Blender is not set up: put its path in config.local.toml.")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(animate_command(blender_exe, repo, rigged_blend, out_dir, previews),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AnimFailed("Making the animations took too long. Press Redo.") from None
    rep_path = out_dir / "clips.json"
    if proc.returncode != 0 or not rep_path.is_file() or "ANIM_OK" not in proc.stdout:
        raise AnimFailed("The animations could not be made for this model. Press Redo; if it "
                         "happens again, build the skeleton again in step 3.")
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    report = check_animated_glb(out_dir / "animated.glb", rep)
    if report.problems:
        raise AnimFailed(" ".join(report.problems))
    notes = [f"The {n} leg is too short to reach the ground (the model holds that foot up), "
             "so that foot steps a little above the ground." for n in rep.get("short_legs", [])]
    return AnimResult(out_dir, rep["template"], rep["clips"], rep["seconds"], report.public(),
                      notes)


__all__ = ["AnimFailed", "AnimResult", "CLIP_NAMES", "LOOPING", "NOT_YET", "animate",
           "animate_command"]
