"""Step 1 limb check: count the legs and arms of a fresh model and compare them with what the
words ask for. The counter is the one Step 3 uses to propose a monster skeleton
(skeleton/limbs.py).

The rule stays simple: a number is expected only where the words state it ("eight legs",
"six-armed", "legless") or the creature's name fixes it (a spider has 8 legs). The model type
alone sets nothing: on people and animals arms often touch the body, and a robe or a tail
can look like an extra leg, so a count there would raise false alarms.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

NUMBERS = {"no": 0, "zero": 0, "one": 1, "single": 1, "two": 2, "three": 3, "four": 4,
           "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
           "twelve": 12}
_NUM = r"(\d{1,2}|" + "|".join(NUMBERS) + r")"
PARTS = {"legs": (r"legs|legged", "legless"), "arms": (r"arms|armed", "armless")}
# creatures whose name alone fixes a count (legs only; claws and feelers vary)
NAMED = {
    "legs": [(r"spiders?|tarantulas?|scorpions?|arachnids?", 8),
             (r"insects?|ants?|beetles?|mantis(?:es)?|cockroach(?:es)?|wasps?|bees?", 6),
             (r"snakes?|serpents?|worms?|slugs?", 0)],
    "arms": [(r"snakes?|serpents?|worms?|slugs?", 0)],
}
SINGULAR = {"legs": ("leg", "legs"), "arms": ("arm", "arms")}


def _num(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word]


def expected_counts(words: str | None) -> dict[str, tuple[int, str]]:
    """{"legs" | "arms": (number, the words that set it)} for what the words fix."""
    text = " ".join((words or "").lower().split())
    out: dict[str, tuple[int, str]] = {}
    for part, (rx, none) in PARTS.items():
        m = re.search(rf"\b{_NUM}[\s-]*(?:{rx})\b", text)
        if m:
            out[part] = (_num(m.group(1)), m.group(0))
            continue
        m = re.search(rf"\b{none}\b", text)
        if m:
            out[part] = (0, m.group(0))
            continue
        for names, n in NAMED[part]:
            m = re.search(rf"\b(?:{names})\b", text)
            if m:
                out[part] = (n, m.group(0))
                break
    return out


def _n(part: str, n: int) -> str:
    one, many = SINGULAR[part]
    return f"{n} {one if n == 1 else many}"


def judge(counts: dict[str, int], expected: dict[str, tuple[int, str]]) -> dict:
    """Compare the counts with what the words ask for; the message is in plain words."""
    problems = []
    for part, (want, why) in expected.items():
        got = counts.get(part, 0)
        if got != want:
            problems.append(f'You asked for "{why}", so it should have {_n(part, want)}, '
                            f"but this model has {_n(part, got)}.")
    message = ""
    if problems:
        message = (" ".join(problems) + " The skeleton step cannot add or remove body parts: "
                   "extra ones stay in the model and missing ones stay missing. "
                   "Press Re-roll for a new try.")
    return {"ok": not problems, "counts": counts,
            "expected": {k: v[0] for k, v in expected.items()}, "problems": problems,
            "message": message}


def check_mesh(mesh: Path, words: str | None, asset_type: str) -> dict | None:
    """Count limbs on a generated mesh. None when there is nothing to check (no number in the
    words and not a monster). A monster is always counted, so Step 3 can show the count."""
    expected = expected_counts(words)
    if not expected and asset_type != "monster":
        return None
    from asset_forge.skeleton.glb import read_mesh
    from asset_forge.skeleton.limbs import count_limbs

    try:
        v, f = read_mesh(Path(mesh))
        counts = count_limbs(v, f)
    except (OSError, ValueError, KeyError, IndexError, MemoryError, struct.error):
        if not expected:
            return None
        return {"ok": False, "counts": {}, "expected": {k: v[0] for k, v in expected.items()},
                "problems": ["The legs and arms could not be counted on this model."],
                "message": "I could not count the legs and arms on this model. Look at it from "
                           "every side before you go on, or press Re-roll for a new try."}
    return judge(counts, expected)
