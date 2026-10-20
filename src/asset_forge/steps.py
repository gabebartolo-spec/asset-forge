"""Hooks for the steps after Generate. Step 2 (Clean) is built elsewhere; this only holds the
exact command the app will run, so the button can be wired to it without a second design."""

from __future__ import annotations

from pathlib import Path


def clean_command(blender_exe: str, repo: Path, raw_glb: Path, out_dir: Path,
                  asset_type: str, ref_png: Path, generator: str | None = None,
                  gpu_lock_dir: Path | None = None) -> list[str]:
    """Writes `<out_dir>/clean.glb` and `<out_dir>/report.json`. `generator` ("hi3dgen" or
    "triposg") tells clean.py which way that maker faces the model. The Clean job itself declares
    0 VRAM (Blender work is CPU); with `gpu_lock_dir` clean.py takes the card's lock only around
    its multiview generator ("clean:multiview" in gpu_lock.VRAM_MB, D-030)."""
    cmd = [
        blender_exe, "-b", "--factory-startup", "-P", str(repo / "blender" / "clean.py"), "--",
        str(raw_glb), str(out_dir), "--type", asset_type, "--ref", str(ref_png),
    ]
    if generator:
        cmd += ["--generator", generator]
    return cmd + (["--gpu-lock", str(gpu_lock_dir)] if gpu_lock_dir else [])
