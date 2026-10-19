import tomllib
from pathlib import Path

import asset_forge

ROOT = Path(__file__).resolve().parents[1]


def test_package_imports_with_version():
    assert asset_forge.__version__


def test_example_config_has_every_section():
    config = tomllib.loads((ROOT / "config.example.toml").read_text(encoding="utf-8"))
    assert {"blender", "godot", "comfyui", "app"} <= config.keys()
    assert config["app"]["host"] == "127.0.0.1", "the app must bind to localhost only"
