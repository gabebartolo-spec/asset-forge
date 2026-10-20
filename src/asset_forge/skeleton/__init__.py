"""Step 3, Skeleton: fit a fixed template to the cleaned model, bind it, strike a test pose.

The app shell calls one function:

    rig(clean_glb, out_dir, asset_type, blender_exe)  ->  RigResult

It runs `blender/rig.py` headless and writes, in out_dir: rigged.glb (the skeleton and weights,
no animation), test_pose.glb (the same with one test-pose clip), rigged.blend, skeleton.json,
and the six-view test-pose sheet (pose_<view>_<clay|colour>.png). `check_rig_glb` re-reads a
rigged .glb and reports every limit it breaks, in plain words (the gate: at most 4 bone
influences per vertex, at most 64 bones).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from asset_forge.skeleton.glb import read_skin
from asset_forge.skeleton.templates import MAX_BONES, MAX_INFLUENCES

REPO = Path(__file__).resolve().parents[3]


class RigFailed(Exception):
    """The rig was not made; the message says so in plain words."""


@dataclass
class RigResult:
    out_dir: Path
    template: str
    bones: int
    weights_method: str
    max_influences: int
    seconds: float
    problems: list[str] = field(default_factory=list)
    limbs: list[dict] = field(default_factory=list)

    def public(self) -> dict:
        return {"template": self.template, "bones": self.bones,
                "weights_method": self.weights_method, "max_influences": self.max_influences,
                "seconds": self.seconds, "problems": self.problems, "limbs": self.limbs}


def rig_command(blender_exe: str, repo: Path, clean_glb: Path, out_dir: Path, asset_type: str,
                template: str | None = None, chain: Path | None = None) -> list[str]:
    cmd = [blender_exe, "-b", "--factory-startup", "-P", str(repo / "blender" / "rig.py"), "--",
           str(clean_glb), str(out_dir), "--type", asset_type]
    if template:
        cmd += ["--template", template]
    if chain:
        cmd += ["--chain", str(chain)]
    return cmd


def check_rig_glb(glb: Path) -> list[str]:
    """Every limit this rigged .glb breaks, in plain words (empty list = passes)."""
    try:
        skin = read_skin(Path(glb))
    except (OSError, ValueError, KeyError) as e:
        return [f"The rigged file could not be read ({e})."]
    problems = []
    if skin.bones == 0:
        problems.append("The model has no skeleton.")
    if skin.bones > MAX_BONES:
        problems.append(f"The skeleton has {skin.bones} bones; the limit is {MAX_BONES}.")
    if skin.max_influences > MAX_INFLUENCES:
        problems.append(f"Some parts of the model follow {skin.max_influences} bones at once; "
                        f"the limit is {MAX_INFLUENCES}.")
    if skin.unweighted_vertices:
        problems.append(f"{skin.unweighted_vertices} points of the model follow no bone.")
    return problems


def rig(clean_glb: Path, out_dir: Path, asset_type: str, blender_exe: str,
        template: str | None = None, repo: Path = REPO, timeout: float = 600,
        chain: Path | None = None) -> RigResult:
    """Run the Skeleton step. Raises RigFailed (plain words) when it cannot finish. A monster
    needs `chain`: the limb chains the user confirmed (see skeleton/monster.py)."""
    clean_glb, out_dir = Path(clean_glb), Path(out_dir)
    if asset_type == "monster" and (chain is None or not Path(chain).is_file()):
        raise RigFailed("Check the limb markers and press Confirm limbs first.")
    if not clean_glb.is_file():
        raise RigFailed("There is no cleaned model yet. Run Clean up first.")
    if not blender_exe or not Path(blender_exe).is_file():
        raise RigFailed("Blender is not set up: put its path in config.local.toml.")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(rig_command(blender_exe, repo, clean_glb, out_dir, asset_type,
                                          template, chain), capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RigFailed("Building the skeleton took too long. Press Redo.") from None
    rep_path = out_dir / "skeleton.json"
    if proc.returncode != 0 or not rep_path.is_file() or "RIG_OK" not in proc.stdout:
        raise RigFailed("The skeleton could not be built for this model. Press Redo; "
                        "if it happens again, try another maker in step 1.")
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    problems = check_rig_glb(out_dir / "rigged.glb")
    if problems:
        raise RigFailed(" ".join(problems))
    w = rep["weights"]
    return RigResult(out_dir, rep["template"], rep["bones"], w["method"], w["max_influences"],
                     rep["seconds"], w["problems"], rep.get("limbs") or [])
