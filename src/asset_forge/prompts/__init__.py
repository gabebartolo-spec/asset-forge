"""Prompt generator ("Expand my idea", D-020): a few words in, a full image prompt out."""

from __future__ import annotations

import re

from . import llm
from .llm import PromptGenError
from .templates import (
    ASSET_TYPES,
    MAX_PROMPT_CHARS,
    MAX_SUBJECT_CHARS,
    SUFFIX,
    SYSTEM,
    TARGETS,
)

__all__ = ["ASSET_TYPES", "TARGETS", "PromptGenError", "expand", "fallback"]


def _check(idea: str, asset_type: str, target: str) -> tuple[str, str, str]:
    idea = " ".join(idea.split())
    asset_type = asset_type.lower()
    if not idea:
        raise PromptGenError("Type a few words first, then press Expand my idea.")
    if asset_type not in ASSET_TYPES:
        raise PromptGenError(f"Unknown type '{asset_type}'. Pick one of: {', '.join(ASSET_TYPES)}.")
    if target not in TARGETS:
        raise PromptGenError(f"Unknown view '{target}'. Pick front or back.")
    if (asset_type, target) not in SUFFIX:
        raise PromptGenError("A back view only exists for sprites.")
    return idea, asset_type, target


def _trim(text: str, limit: int) -> str:
    """One line, no quotes or list marks, cut at a word boundary under the cap."""
    lines = text.strip().splitlines()
    text = lines[0] if lines else ""
    text = re.sub(r"^[\s\-*\d.)\"'`]+|[\s\"'`]+$", "", text)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text.rstrip(" .,;:")
    return text[:limit].rsplit(" ", 1)[0].rstrip(" .,;:")


def _assemble(subject: str, asset_type: str, target: str) -> str:
    subject = _trim(subject, MAX_SUBJECT_CHARS)
    return f"{subject}, {SUFFIX[(asset_type, target)]}"[:MAX_PROMPT_CHARS]


def fallback(idea: str, asset_type: str, target: str = "front") -> str:
    """The prompt without a model: the user's words plus the fixed view words."""
    idea, asset_type, target = _check(idea, asset_type, target)
    return _assemble(idea, asset_type, target)


def expand(
    idea: str, asset_type: str, target: str = "front", *, allow_fallback: bool = False
) -> str:
    """Return one full prompt for `idea`. Deterministic (greedy decoding).

    asset_type: humanoid, monster, animal or sprite. target: front, or back (sprites only).
    If the local model is not installed this raises PromptGenError naming the fix; with
    allow_fallback=True it returns the plain template prompt instead.
    """
    idea, asset_type, target = _check(idea, asset_type, target)
    try:
        subject = llm.generate(SYSTEM[asset_type], idea, asset_type)
    except PromptGenError:
        if allow_fallback:
            return _assemble(idea, asset_type, target)
        raise
    return _assemble(_trim(subject, MAX_SUBJECT_CHARS) or idea, asset_type, target)
