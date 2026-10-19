"""export(asset_dir, asset_type): refuse unless the gates and the Godot check pass."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from asset_forge.export import godot_check


class ExportRefused(Exception):
    """The export did not happen; `reasons` are plain-words broken limits."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def _gate_problems(report: dict, asset_type: str) -> list[str]:
    from asset_forge.gates import check  # lazy: owned by the clean step

    return check(report, asset_type)


def export(asset_dir: Path, asset_type: str, exports_dir: Path | None = None,
           godot_exe: Path | None = None) -> Path:
    """Copy the cleaned .glb (+ .blend) to exports/<asset-id>/ once both checks pass.

    asset_dir holds the cleaned `<id>.glb`, optional `<id>.blend` and `report.json`.
    Returns the export folder. Raises ExportRefused (nothing is copied) on any failure.
    """
    asset_dir = Path(asset_dir)
    asset_id = asset_dir.name
    glb = asset_dir / f"{asset_id}.glb"
    if not glb.is_file():
        raise ExportRefused([f"There is no cleaned model ({glb.name}) to export. Run Clean first."])
    report_path = asset_dir / "report.json"
    if not report_path.is_file():
        raise ExportRefused(["The clean step left no report, so the limits cannot be checked. "
                             "Run Clean again."])
    report = json.loads(report_path.read_text(encoding="utf-8"))

    reasons = list(_gate_problems(report, asset_type))
    godot = godot_check.check_glb(glb, exe=godot_exe)
    if not godot.ok:
        reasons += [f"Godot could not load the model cleanly: {p}" for p in godot.problems]
    if reasons:
        raise ExportRefused(reasons)

    dest = (exports_dir or Path("exports")) / asset_id
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, dest / glb.name)
    blend = asset_dir / f"{asset_id}.blend"
    if blend.is_file():
        shutil.copy2(blend, dest / blend.name)
    return dest
