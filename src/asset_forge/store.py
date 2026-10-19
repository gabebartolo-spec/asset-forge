"""The library: `library/<asset-id>/<step>/` holds each step's outputs, `settings.json` (what was
asked for) and the seed, so any step can be redone without redoing earlier ones.

    library/<asset-id>/asset.json              id, type, created, last step reached
    library/<asset-id>/generate/input.png      the cut-out reference the generator saw
    library/<asset-id>/generate/settings.json  generator, seed, type
    library/<asset-id>/generate/status.json    the latest job: state, message, times, error
    library/<asset-id>/generate/raw.glb        the raw mesh
    library/<asset-id>/generate/result.json    time, VRAM peak, generator details
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

ASSET_TYPES = ("humanoid", "monster", "animal")
STEPS = ("generate", "clean", "skeleton", "animate")
_ID = re.compile(r"^a-\d{8}-\d{6}-[0-9a-f]{4}$")


class NotFound(KeyError):
    pass


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Store:
    def __init__(self, library_dir: Path) -> None:
        self.root = Path(library_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    # assets
    def asset_dir(self, asset_id: str) -> Path:
        if not _ID.match(asset_id):
            raise NotFound(asset_id)
        d = self.root / asset_id
        if not d.is_dir():
            raise NotFound(asset_id)
        return d

    def step_dir(self, asset_id: str, step: str) -> Path:
        if step not in STEPS:
            raise NotFound(step)
        return self.asset_dir(asset_id) / step

    def create_asset(self, asset_type: str, image_png: bytes) -> dict:
        if asset_type not in ASSET_TYPES:
            raise ValueError("Choose Humanoid, Monster or Animal.")
        asset_id = f"a-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
        d = self.root / asset_id
        (d / "generate").mkdir(parents=True)
        (d / "generate" / "input.png").write_bytes(image_png)
        asset = {"id": asset_id, "type": asset_type, "created": time.time(), "reached": None}
        _write_json(d / "asset.json", asset)
        return asset

    def get_asset(self, asset_id: str) -> dict:
        d = self.asset_dir(asset_id)
        asset = _read_json(d / "asset.json")
        asset["steps"] = {}
        for step in STEPS:
            sd = d / step
            if not sd.is_dir():
                continue
            info: dict[str, Any] = {}
            for name in ("settings", "status", "result"):
                f = sd / f"{name}.json"
                if f.exists():
                    info[name] = _read_json(f)
            info["files"] = sorted(p.name for p in sd.iterdir() if p.is_file())
            asset["steps"][step] = info
        return asset

    def list_assets(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if d.is_dir() and _ID.match(d.name) and (d / "asset.json").exists():
                out.append(_read_json(d / "asset.json"))
        return out

    def mark_reached(self, asset_id: str, step: str) -> None:
        d = self.asset_dir(asset_id)
        asset = _read_json(d / "asset.json")
        asset["reached"] = step
        _write_json(d / "asset.json", asset)

    # step records
    def write_settings(self, asset_id: str, step: str, settings: dict) -> None:
        _write_json(self.step_dir(asset_id, step) / "settings.json", settings)

    def read_settings(self, asset_id: str, step: str) -> dict:
        return _read_json(self.step_dir(asset_id, step) / "settings.json")

    def write_status(self, asset_id: str, step: str, status: dict) -> None:
        _write_json(self.step_dir(asset_id, step) / "status.json", status)

    def write_result(self, asset_id: str, step: str, result: dict) -> None:
        _write_json(self.step_dir(asset_id, step) / "result.json", result)

    def file_path(self, asset_id: str, step: str, name: str) -> Path:
        if "/" in name or "\\" in name or name.startswith("."):
            raise NotFound(name)
        p = self.step_dir(asset_id, step) / name
        if not p.is_file():
            raise NotFound(name)
        return p

    def fail_unfinished(self) -> int:
        """After a restart no job is really running: mark leftovers failed, in plain words."""
        n = 0
        for a in self.list_assets():
            for step in STEPS:
                f = self.root / a["id"] / step / "status.json"
                if f.exists():
                    st = _read_json(f)
                    if st.get("state") in ("queued", "waiting", "running"):
                        st.update(
                            state="failed",
                            message="Asset Forge was closed before this finished. Press Redo.",
                            error="Asset Forge was closed before this finished. Press Redo.",
                        )
                        _write_json(f, st)
                        n += 1
        return n
