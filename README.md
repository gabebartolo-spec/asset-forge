# Asset Forge

Local, free tool: a text prompt or reference image in; out comes a game-ready 3D model (clean
mesh, skeleton, idle/walk/run/attack/hit/faint animations, `.glb` for Godot) or a pixel-perfect
Pokémon-style sprite.

Status: Phase 0 (foundations). The design is
[docs/superpowers/specs/2026-10-19-asset-forge-design.md](docs/superpowers/specs/2026-10-19-asset-forge-design.md).

## Dev setup

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
cp config.example.toml config.local.toml   # then edit paths
.venv/Scripts/python -m pytest
```

Needs Windows with an NVIDIA GPU (12 GB), Blender 5.2, and Godot 4.7.2 for export checks.
