"""Runs the local model in its own env (models/envs/promptgen) so the app never imports torch."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .templates import FEWSHOT

MODEL_ID = "Qwen/Qwen3-1.7B"  # Apache-2.0, see docs/LICENCES.md
TIMEOUT_S = 120
LAST_STATS: dict[str, float] = {}  # load_s, gen_s, vram_mb of the latest call (for the CLI)


class PromptGenError(RuntimeError):
    """A plain-words error the UI can show as is."""


def models_dir() -> Path:
    env = os.environ.get("FORGE_MODELS_DIR")
    if env:
        return Path(env)
    repo = Path(__file__).resolve().parents[3]
    main = repo.parent.parent / "asset-forge" / "models"  # worktrees share the main models/
    return main if main.is_dir() else repo / "models"


def env_python() -> Path:
    return models_dir() / "envs" / "promptgen" / "Scripts" / "python.exe"


def build_messages(system: str, idea: str, asset_type: str) -> list[dict[str, str]]:
    ex_in, ex_out = FEWSHOT[asset_type]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": ex_in},
        {"role": "assistant", "content": ex_out},
        {"role": "user", "content": idea},
    ]


def generate(system: str, idea: str, asset_type: str) -> str:
    py = env_python()
    if not py.exists():
        raise PromptGenError(
            "The prompt writer is not installed. Create models/envs/promptgen with uv, install "
            f"torch and transformers into it, and download {MODEL_ID} into models/hf "
            "(steps in docs/LICENCES.md and the prompts module docstring)."
        )
    job = {
        "model": MODEL_ID,
        "messages": build_messages(system, idea, asset_type),
        "max_new_tokens": 90,
    }
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "HF_HOME": str(models_dir() / "hf"),
        "HF_HUB_OFFLINE": "1",
    }
    try:
        done = subprocess.run(
            [str(py), "-m", "asset_forge.prompts.worker"],
            input=json.dumps(job),
            text=True,
            capture_output=True,
            timeout=TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PromptGenError("The prompt writer took too long. Try again.") from exc
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["no detail"]
        raise PromptGenError(
            f"The prompt writer failed ({tail[0][:160]}). Check that {MODEL_ID} is downloaded "
            "into models/hf and the GPU is free."
        )
    try:
        data = json.loads(done.stdout.strip().splitlines()[-1])
        LAST_STATS.update({k: data[k] for k in ("load_s", "gen_s", "vram_mb")})
        return data["text"]
    except (ValueError, KeyError, IndexError) as exc:
        raise PromptGenError("The prompt writer gave an unreadable answer. Try again.") from exc
