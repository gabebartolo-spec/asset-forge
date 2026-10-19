"""Settings: defaults, overridden by the gitignored `config.local.toml` (template:
`config.example.toml`) and by environment variables. Nothing machine-specific is committed."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The menu order is the director's (D-018, D-019): Hi3DGen first (preselected), then TripoSG.
DEFAULT_GENERATOR_ORDER = ["hi3dgen", "triposg"]


@dataclass
class Settings:
    repo: Path = REPO
    models_dir: Path = REPO / "models"
    library_dir: Path = REPO / "library"
    host: str = "127.0.0.1"
    port: int = 7860
    generator_order: list[str] = field(default_factory=lambda: list(DEFAULT_GENERATOR_ORDER))
    blender_exe: str = ""

    @property
    def lock_dir(self) -> Path:
        return self.models_dir / "gpu.lock"

    @property
    def web_dir(self) -> Path:
        return self.repo / "web"


def _default_models_dir() -> Path:
    # Worktrees share the main checkout's gitignored models/ folder (same rule as tools/bakeoff).
    env = os.environ.get("FORGE_MODELS_DIR")
    if env:
        return Path(env)
    here = REPO / "models"
    if here.is_dir():
        return here
    main = REPO.parent.parent / "asset-forge" / "models"
    return main if main.is_dir() else here


def load_settings(config_path: Path | None = None) -> Settings:
    s = Settings(models_dir=_default_models_dir())
    path = config_path or REPO / "config.local.toml"
    if path.is_file():
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
        app = cfg.get("app", {})
        s.host = app.get("host", s.host)
        s.port = int(app.get("port", s.port))
        if "library_dir" in app:
            s.library_dir = REPO / app["library_dir"]
        if "models_dir" in app:
            s.models_dir = Path(app["models_dir"])
        s.generator_order = list(cfg.get("generators", {}).get("order", s.generator_order))
        s.blender_exe = cfg.get("blender", {}).get("exe", s.blender_exe)
    if os.environ.get("FORGE_MODELS_DIR"):
        s.models_dir = Path(os.environ["FORGE_MODELS_DIR"])
    if os.environ.get("FORGE_LIBRARY_DIR"):
        s.library_dir = Path(os.environ["FORGE_LIBRARY_DIR"])
    s.host = "127.0.0.1"  # localhost only, always (design 5.1); not configurable
    return s
