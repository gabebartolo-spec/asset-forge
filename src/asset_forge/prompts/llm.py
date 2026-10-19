"""Runs the local model in its own env (models/envs/promptgen) so the app never imports torch."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .templates import FEWSHOT

MODEL_ID = "Qwen/Qwen3-1.7B"  # Apache-2.0, see docs/LICENCES.md
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
    job = {"messages": build_messages(system, idea, asset_type), "max_new_tokens": 90}
    try:
        proc = _worker(py)
        proc.stdin.write(json.dumps(job) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise BrokenPipeError(_stderr_tail(proc))
        data = json.loads(line)
        LAST_STATS.update({k: data[k] for k in ("load_s", "gen_s", "vram_mb")})
        return data["text"]
    except (OSError, ValueError, KeyError) as exc:
        stop()
        raise PromptGenError(
            f"The prompt writer failed ({str(exc)[:160] or 'no detail'}). Check that {MODEL_ID} "
            "is downloaded into models/hf and the GPU is free."
        ) from exc


_proc: subprocess.Popen[str] | None = None
_errlog = tempfile.TemporaryFile(mode="w+")  # worker stderr, read only on failure


def _stderr_tail(proc: subprocess.Popen[str]) -> str:
    try:
        proc.wait(timeout=2)
        _errlog.seek(0)
        tail = _errlog.read().strip().splitlines()[-1:]
        return tail[0] if tail else "worker exited"
    except (subprocess.TimeoutExpired, OSError):
        return "worker exited"


def _worker(py: Path) -> subprocess.Popen[str]:
    """Start the resident worker once; later calls reuse it (about 1 s instead of 15 s)."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return _proc
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "HF_HOME": str(models_dir() / "hf"),
        "HF_HUB_OFFLINE": "1",
    }
    _proc = subprocess.Popen(
        [str(py), "-m", "asset_forge.prompts.worker", MODEL_ID],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=_errlog,
        text=True,
        env=env,
    )
    ready = _proc.stdout.readline()
    if not ready:
        raise BrokenPipeError(_stderr_tail(_proc))
    LAST_STATS["load_s"] = json.loads(ready)["load_s"]
    return _proc


def stop() -> None:
    """Free the GPU: end the resident worker (call when the app closes or the GPU is needed)."""
    global _proc
    if _proc is not None:
        try:
            _proc.stdin.close()
            _proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            _proc.kill()
    _proc = None
