"""The round-3 pair gates, shown failing on the round-2 bad backs (real sprites from PR #11)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from asset_forge.sprites.pairqa import (
    check_anatomy_match,
    check_back_faces_away,
    check_back_has_no_face,
)
from asset_forge.sprites.presets import PRESETS

from .fixtures import good_sprite

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sprites"


def load(subject: str, preset: str, view: str) -> np.ndarray:
    return np.array(Image.open(FIX / f"r2_{subject}_{preset}_{view}.png").convert("RGBA"))


def words(problems: list[str]) -> str:
    return " ".join(problems)


PAIRS = [
    ("lizard", "southern_cross"),
    ("lizard", "gba"),
    ("bird", "southern_cross"),
    ("bird", "gba"),
]


@pytest.mark.parametrize(("subject", "preset"), PAIRS)
def test_no_face_gate_fails_every_round_two_back(subject, preset):
    """Round-2 verdict: the bird backs show beak and eye, the lizard SC back shows its eyes,
    the lizard GBA back keeps the front's face colours."""
    problems, m = check_back_has_no_face(
        load(subject, preset, "front"), load(subject, preset, "back")
    )
    assert problems, m
    assert "back" in words(problems)


@pytest.mark.parametrize(("subject", "preset"), [("lizard", "southern_cross"), ("lizard", "gba")])
def test_anatomy_gate_fails_the_round_two_lizards(subject, preset):
    """Round-2 verdict: front and back were different bodies (limbs, tail, stance)."""
    problems, m = check_anatomy_match(load(subject, preset, "front"), load(subject, preset, "back"))
    assert problems, m


def test_anatomy_counts_come_out_in_the_metrics():
    _, m = check_anatomy_match(load("lizard", "gba", "front"), load("lizard", "gba", "back"))
    assert {"front_limb_blobs", "back_limb_blobs", "front_stance", "back_stance"} <= set(m)
    assert m["front_ground_contacts"] == 3 and m["back_ground_contacts"] == 1


def test_a_real_back_view_passes_both_gates():
    sc = PRESETS["southern_cross"]
    front, back = good_sprite(sc, "front"), good_sprite(sc, "back")
    assert check_back_has_no_face(front, back)[0] == []
    assert check_anatomy_match(front, back)[0] == []
    assert check_back_faces_away(back)[0] == []


def test_the_front_copied_as_the_back_shows_a_face():
    sc = PRESETS["southern_cross"]
    front = good_sprite(sc, "front")
    problems, _ = check_back_has_no_face(front, front)
    assert "both eyes" in words(problems)


def test_a_back_with_a_beak_painted_on_fails():
    sc = PRESETS["southern_cross"]
    front, back = good_sprite(sc, "front"), good_sprite(sc, "back").copy()
    eye = front[np.all(front[..., :3] == (10, 140, 150), axis=2) & (front[..., 3] > 0)]
    assert len(eye)  # the fixture front has teal eyes
    head_y = np.nonzero(back[..., 3])[0].min() + 10
    back[head_y : head_y + 3, 36:46, :3] = (10, 140, 150)  # an eye-coloured patch on the head
    problems, _ = check_back_has_no_face(front, back)
    assert "still shows a face" in words(problems)


def test_a_profile_is_not_a_back():
    sc = PRESETS["southern_cross"]
    problems, m = check_back_faces_away(good_sprite(sc, "side"))
    assert "side view" in words(problems) and m["back_symmetry"] < 0.55


def test_anatomy_gate_catches_a_tail_less_standing_back():
    sc = PRESETS["southern_cross"]
    front = good_sprite(sc, "front")
    thin = np.zeros_like(front)
    thin[10:70, 36:44] = (200, 90, 40, 255)  # one tall pole: wrong stance, one contact
    thin[10:70, 35:45, 3] = 255
    problems, _ = check_anatomy_match(front, thin)
    assert "stance" in words(problems) or "stands on" in words(problems)
