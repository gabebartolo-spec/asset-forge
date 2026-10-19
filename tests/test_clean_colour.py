"""Clean step colour: registration, left-right mirror, shadow-free fill, albedo truth. Local only
(`pytest -m blender`). CLEAN_SCRIPT overrides the script under test."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from test_clean_forward import blender
from test_clean_step import FIX, ROOT

pytestmark = pytest.mark.blender
PROBE = FIX / "colour_probe.py"
CLEAN = Path(os.environ.get("CLEAN_SCRIPT", ROOT / "blender" / "clean.py"))


def probe(mode, tmp_path):
    out = tmp_path / f"{mode}.json"
    blender("-P", str(PROBE), "--", mode, str(CLEAN), str(out))
    return json.loads(out.read_text())


def luma(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def test_face_drawn_left_of_centre_lands_on_the_centred_head(tmp_path):
    r = probe("head", tmp_path)
    assert r["n"] > 10
    red, green, _ = r["mean_rgb"]
    assert red - green > 0.2  # the red face disc (r-g 0.8), not tan head (0.1) or blue body


def test_head_that_does_not_match_the_picture_gets_no_face(tmp_path):
    r = probe("headtiny", tmp_path)
    assert r["stats"]["registration"]["head_painted_from_reference"] is False
    red, green, _ = r["mean_rgb"]
    assert red - green < 0.3  # no misplaced face; low-frequency colour instead


def test_side_projected_animal_mirrors_left_right_only(tmp_path):
    r = probe("animal", tmp_path)
    assert r["far_n"] > 10 and r["back_n"] > 10
    assert r["far_min_luma"] < 0.25      # the far flank got the second eye
    assert r["back_min_luma"] > 0.25     # the back is plain: no eye, no face copied onto it
    assert r["back_std"] < 0.1


def test_fill_ignores_shadow_dark_reference_pixels(tmp_path):
    r = probe("rim", tmp_path)
    assert r["back_n"] > 100
    assert r["back_mean_luma"] > 0.9 * luma((0.8, 0.6, 0.55))  # the dark rim strip did not tint it


def test_albedo_and_lit_sheet_are_true_to_the_reference(tmp_path):
    blender("-P", str(CLEAN), "--", str(FIX / "figure.obj"), str(tmp_path), "--type", "humanoid",
            "--ref", str(FIX / "figure_ref.png"))
    rep = json.loads((tmp_path / "report.json").read_text())
    ref = np.asarray(Image.open(FIX / "figure_ref.png").convert("RGBA"), np.float64) / 255
    ref_rgb = ref[ref[..., 3] > 0.5][:, :3]
    ref_luma = (ref_rgb @ [0.2126, 0.7152, 0.0722]).mean()
    ref_sat = ((ref_rgb.max(axis=1) - ref_rgb.min(axis=1)) / np.maximum(ref_rgb.max(axis=1), 1e-6)
               ).mean()
    shot = np.asarray(Image.open(tmp_path / "after" / "front_colour.png").convert("RGB"),
                      np.float64) / 255
    body = np.abs(shot - shot[2, 2]).sum(axis=2) > 0.06
    inner = body.copy()  # drop the anti-aliased rim: it blends in the background grey
    for sh in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        inner &= np.roll(body, sh, (0, 1))
    body = inner
    lit = shot[body]
    lit_luma = (lit @ [0.2126, 0.7152, 0.0722]).mean()
    lit_sat = ((lit.max(axis=1) - lit.min(axis=1)) / np.maximum(lit.max(axis=1), 1e-6)).mean()
    assert 0.85 < lit_luma / ref_luma < 1.2, (lit_luma, ref_luma)
    assert 0.8 < lit_sat / ref_sat < 1.25, (lit_sat, ref_sat)
    for band in rep["albedo_vs_reference"]:  # the saved texture itself, read back from the PNG
        assert 0.8 < band["luma_ratio"] < 1.25
        assert 0.75 < band["sat_ratio"] < 1.3
