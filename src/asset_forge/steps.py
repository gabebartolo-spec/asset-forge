"""Hooks for the steps after Generate. Step 2 (Clean) is built elsewhere; this only holds the
exact command the app will run, so the button can be wired to it without a second design."""

from __future__ import annotations

from pathlib import Path


def multiview_paths(models_dir: Path) -> dict[str, Path]:
    """Where the multiview colour generator (method B) lives in the gitignored models/ folder."""
    return {"python": models_dir / "envs" / "sdxl" / "Scripts" / "python.exe",
            "src": models_dir / "src" / "mv_adapter",
            "hf_home": models_dir / "hf"}


def clean_command(blender_exe: str, repo: Path, raw_glb: Path, out_dir: Path,
                  asset_type: str, ref_png: Path, gpu_lock_dir: Path | None = None,
                  generator: str | None = None, models_dir: Path | None = None) -> list[str]:
    """Writes `<out_dir>/clean.glb` and `<out_dir>/report.json`. With `models_dir` the hidden sides
    are coloured by the multiview generator (method B, the default route) and the card's lock is
    `models_dir/gpu.lock` unless `gpu_lock_dir` says otherwise. The Clean job itself declares 0
    VRAM (Blender work is CPU); with a lock dir clean.py holds the card only around its multiview
    generator ("clean:multiview" in gpu_lock.VRAM_MB, D-030)."""
    cmd = [
        blender_exe, "-b", "--factory-startup", "-P", str(repo / "blender" / "clean.py"), "--",
        str(raw_glb), str(out_dir), "--type", asset_type, "--ref", str(ref_png),
    ]
    if generator:
        cmd += ["--generator", generator]
    if models_dir is not None:
        mv = multiview_paths(models_dir)
        cmd += ["--mv-python", str(mv["python"]), "--mv-src", str(mv["src"]),
                "--hf-home", str(mv["hf_home"])]
        gpu_lock_dir = gpu_lock_dir or models_dir / "gpu.lock"
    return cmd + (["--gpu-lock", str(gpu_lock_dir)] if gpu_lock_dir else [])
