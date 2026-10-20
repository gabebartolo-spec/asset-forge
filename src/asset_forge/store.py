"""The library: `library/<asset-id>/<step>/` holds each step's outputs, `settings.json` (what was
asked for) and the seed, so any step can be redone without redoing earlier ones.

    library/<asset-id>/asset.json              id, type, created, last step reached, prompt
                                               (prompt only for text-only assets), timings
                                               (seconds the latest run of each step took)
    library/_trash/<asset-id>/                 a removed asset, whole; Put back moves it home
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
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ASSET_TYPES = ("humanoid", "monster", "animal")
TRASH = "_trash"
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
        self._mu = threading.Lock()  # asset.json is read-modify-written from several threads

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

    def create_text_asset(self, asset_type: str, prompt: str) -> dict:
        """An asset that starts from words: the reference picture is drawn later (draw.py)."""
        if asset_type not in ASSET_TYPES:
            raise ValueError("Choose Humanoid, Monster or Animal.")
        asset_id = f"a-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
        d = self.root / asset_id
        (d / "generate").mkdir(parents=True)
        asset = {"id": asset_id, "type": asset_type, "created": time.time(), "reached": None,
                 "prompt": prompt}
        _write_json(d / "asset.json", asset)
        return asset

    def set_prompt(self, asset_id: str, prompt: str) -> None:
        self._update(asset_id, lambda a: a.update(prompt=prompt))

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
        self._update(asset_id, lambda a: a.update(reached=step))

    def record_timing(self, asset_id: str, key: str, seconds: float) -> None:
        """Seconds the latest run of a step took (keys: draw, generate, clean, skeleton)."""
        def put(a: dict) -> None:
            a.setdefault("timings", {})[key] = round(seconds, 1)
        self._update(asset_id, put)

    def _update(self, asset_id: str, change: Callable[[dict], Any]) -> None:
        d = self.asset_dir(asset_id)
        with self._mu:
            asset = _read_json(d / "asset.json")
            change(asset)
            _write_json(d / "asset.json", asset)

    # library: cards, duplicate, trash (never a hard delete)
    @property
    def trash_dir(self) -> Path:
        return self.root / TRASH

    def card(self, d: Path) -> dict:
        """One Library entry: asset.json plus a thumbnail flag and what it is doing now."""
        asset = _read_json(d / "asset.json")
        asset["thumb"] = (d / "generate" / "input.png").is_file()
        states = []
        for step in STEPS:
            f = d / step / "status.json"
            if f.exists():
                states.append(_read_json(f))
        asset["busy"] = any(st.get("state") in ("queued", "waiting", "running") for st in states)
        failed = [st for st in states if st.get("state") == "failed"]
        asset["failed"] = (failed[-1].get("error") or failed[-1].get("message")
                           if failed and not asset["busy"] and not asset.get("reached") else None)
        return asset

    def cards(self, trashed: bool = False) -> list[dict]:
        base = self.trash_dir if trashed else self.root
        if not base.is_dir():
            return []
        out = []
        for d in sorted(base.iterdir(), reverse=True):
            if d.is_dir() and _ID.match(d.name) and (d / "asset.json").exists():
                out.append(self.card(d))
        return out

    def duplicate(self, asset_id: str) -> dict:
        src = self.asset_dir(asset_id)
        new_id = f"a-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
        shutil.copytree(src, self.root / new_id)
        with self._mu:
            a = _read_json(self.root / new_id / "asset.json")
            a.update(id=new_id, created=time.time(), copied_from=asset_id)
            _write_json(self.root / new_id / "asset.json", a)
        return a

    def trash(self, asset_id: str) -> None:
        src = self.asset_dir(asset_id)
        self.trash_dir.mkdir(exist_ok=True)
        shutil.move(str(src), str(self.trash_dir / asset_id))

    def restore(self, asset_id: str) -> None:
        if not _ID.match(asset_id) or not (self.trash_dir / asset_id).is_dir():
            raise NotFound(asset_id)
        shutil.move(str(self.trash_dir / asset_id), str(self.root / asset_id))

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
        """A step's output by name; one sub-folder is allowed (clean/after/front_clay.png)."""
        parts = name.split("/")
        if len(parts) > 2 or "\\" in name or any(not s or s.startswith(".") for s in parts):
            raise NotFound(name)
        p = self.step_dir(asset_id, step).joinpath(*parts)
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
