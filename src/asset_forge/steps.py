"""Hooks for the steps after Generate. Step 2 (Clean) is built elsewhere; this only holds the
exact command the app will run, so the button can be wired to it without a second design."""

from __future__ import annotations

from pathlib import Path


def clean_command(blender_exe: str, repo: Path, raw_glb: Path, out_dir: Path,
                  asset_type: str, ref_png: Path) -> list[str]:
    """Writes `<out_dir>/clean.glb` and `<out_dir>/report.json`."""
    return [
        blender_exe, "-b", "--factory-startup", "-P", str(repo / "blender" / "clean.py"), "--",
        str(raw_glb), str(out_dir), "--type", asset_type, "--ref", str(ref_png),
    ]
