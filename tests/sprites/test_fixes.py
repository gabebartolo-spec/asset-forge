"""QA-verdict fixes: shadow, accents, pinholes, shared palette, speckle, same-creature check."""

import numpy as np
import pytest

from asset_forge.sprites import SpriteFailed, check_sprite, export_pair, make_pair
from asset_forge.sprites.presets import OUTLINE_COLOUR, get_preset

from .fixtures import BODY, FakeDrawer, good_sprite, native_creature, raw_generated

SC = get_preset("southern_cross")
TEAL = (20, 200, 190)


def words(problems):
    return " | ".join(problems)


def test_enclosed_ground_shadow_is_removed_with_the_open_one():
    from asset_forge.sprites.post import remove_background

    img = native_creature().copy()
    yy, xx = np.mgrid[0:128, 0:128]
    shadow = ((yy - 112) / 5.0) ** 2 + ((xx - 60) / 30.0) ** 2 <= 1
    img[shadow & (img.sum(axis=2) == 765)] = (150, 150, 149)
    img[66:70, 56:62] = (151, 150, 149)  # same drop-shadow grey, enclosed by the body
    rgba = remove_background(img)
    assert rgba[112, 60, 3] == 0
    assert rgba[67, 58, 3] == 0, "the enclosed grey must go too"
    assert rgba[75, 60, 3] == 255 and rgba[60, 70, 3] == 255  # the body stays


def test_a_grey_creature_without_a_shadow_is_kept():
    from asset_forge.sprites.post import remove_background

    img = native_creature().copy()
    img[(img == BODY).all(axis=2)] = (150, 150, 150)
    assert remove_background(img)[70, 40, 3] == 255


def test_small_saturated_accent_survives_palette_reduction():
    from asset_forge.sprites.post import reduce_palette

    rng = np.random.default_rng(4)
    base = rng.integers(60, 200, (40, 40, 1)) + rng.integers(0, 12, (40, 40, 3))
    base = base + np.array([30, 0, 0])
    s = np.dstack([np.clip(base, 0, 255), np.full((40, 40), 255)]).astype(np.uint8)
    s[10:12, 10:12, :3] = TEAL  # a 4 px eye on a 1600 px body
    out = reduce_palette(s, 8)
    assert len(np.unique(out[..., :3].reshape(-1, 3), axis=0)) <= 8
    assert np.abs(out[10:12, 10:12, :3].astype(int) - TEAL).max() <= 40, "the eye lost its colour"


def test_corner_touching_pinhole_is_filled():
    from asset_forge.sprites.post import fill_holes

    s = np.zeros((30, 30, 4), np.uint8)
    s[5:25, 5:25] = (200, 90, 40, 255)
    s[5:10, 9] = 0  # a notch from the top edge ...
    s[10, 10] = 0  # ... and a pixel that only touches it at a corner
    out = fill_holes(s)
    assert out[10, 10, 3] == 255
    assert out[7, 9, 3] == 0  # the real notch is left alone


def test_check_counts_a_corner_touching_gap_as_a_hole():
    s = np.zeros((96, 96, 4), np.uint8)
    s[10:80, 10:80] = (200, 90, 40, 255)
    s[10:16, 40] = 0  # a notch from the top edge ...
    s[16, 41] = 0  # ... and a pixel touching it only at a corner
    assert "1 holes" in words(check_sprite(s, SC))


def test_one_palette_for_the_pair():
    from asset_forge.sprites.post import reduce_palette_shared

    rng = np.random.default_rng(5)

    def sprite(shift):
        base = np.clip(rng.integers(40, 200, (32, 32, 3)) + shift, 0, 255)
        return np.dstack([base, np.full((32, 32), 255)]).astype(np.uint8)

    a, b = reduce_palette_shared([sprite(30), sprite(10)], 10)
    ca = {tuple(c) for c in np.unique(a[..., :3].reshape(-1, 3), axis=0)}
    cb = {tuple(c) for c in np.unique(b[..., :3].reshape(-1, 3), axis=0)}
    assert len(ca | cb) <= 10
    assert len(ca & cb) >= 5


def test_speckle_is_cleaned_inside_but_outline_and_accent_stay():
    from asset_forge.sprites.post import clean_speckle, isolated_share

    s = good_sprite(SC)
    solid = s[..., 3] > 0
    rng = np.random.default_rng(1)
    ys, xs = np.nonzero(solid)
    inner = [
        (y, x) for y, x in zip(ys, xs, strict=True) if solid[y - 3 : y + 4, x - 3 : x + 4].all()
    ]
    for i in rng.choice(len(inner), 200, replace=False):
        y, x = inner[i]
        s[y, x, :3] = (250, 240, 200)
    ey = ys.min() + 14
    s[ey : ey + 2, 40:42, :3] = TEAL  # a 2x2 eye
    before = isolated_share(s)
    out = clean_speckle(s)
    assert before > 0.03 and isolated_share(out) < 0.03
    assert np.array_equal(out[..., 3], s[..., 3])
    assert (out[ey : ey + 2, 40:42, :3] == TEAL).all()
    assert (s[..., :3] == OUTLINE_COLOUR).all(axis=2).sum() == (
        (out[..., :3] == OUTLINE_COLOUR).all(axis=2).sum()
    )


def test_same_creature_check():
    from asset_forge.sprites.qa import check_same_creature

    front, back = good_sprite(SC, "front"), good_sprite(SC, "back")
    problems, m = check_same_creature(front, back)
    assert problems == [] and {"colour_distance", "aspect_ratio", "mass_ratio"} <= set(m)
    other = back.copy()
    other[other[..., 3] > 0, :3] = (40, 90, 220)  # a blue creature
    assert "colours" in words(check_same_creature(front, other)[0])
    thin = np.zeros_like(back)
    thin[10:90, 44:52] = (*BODY, 255)  # tall, thin
    assert "shape" in words(check_same_creature(front, thin)[0])
    tiny = np.zeros_like(back)
    tiny[40:50, 40:55] = (*BODY, 255)
    assert check_same_creature(front, tiny)[0]


def test_back_is_drawn_from_the_front_in_one_batch():
    d = FakeDrawer(noise=4)
    make_pair("a small fire lizard creature", d, "southern_cross", seed=2)
    back_inits = [i for (v, _), i in zip(d.calls, d.inits, strict=True) if v == "back"]
    assert back_inits and all(i is not None for i in back_inits)
    assert max(d.batches) >= 2


def test_first_passing_candidate_of_the_batch_is_kept():
    class Mixed(FakeDrawer):
        def draw(self, subject, view, seed, init=None):
            img = super().draw(subject, view, seed, init)
            if view == "back" and seed == 1001:  # first candidate: a copy of the front
                return raw_generated("front", noise=self.noise)
            return img

    res = make_pair("x", Mixed(), "southern_cross", seed=1)
    assert res.seeds["back"] != 1001 and res.metrics["back"]["candidates_tried"] >= 2


def test_export_refuses_a_back_of_another_creature(tmp_path):
    res = make_pair("x", FakeDrawer(), "southern_cross", seed=1)
    res.back = res.back.copy()
    res.back[res.back[..., 3] > 0, :3] = (40, 90, 220)
    with pytest.raises(SpriteFailed) as e:
        export_pair(res, "Bad", tmp_path)
    assert "colours differ" in str(e.value)


def test_a_side_view_front_is_rejected_and_a_facing_one_passes():
    from asset_forge.sprites.qa import check_front_faces_viewer

    assert check_front_faces_viewer(good_sprite(SC, "front"))[0] == []
    problems, m = check_front_faces_viewer(good_sprite(SC, "side"))
    assert "side view" in words(problems) and m["front_symmetry"] < 0.55


def test_the_front_is_redrawn_until_it_faces_the_viewer():
    class Profile(FakeDrawer):
        def draw(self, subject, view, seed, init=None):
            img = super().draw(subject, view, seed, init)
            if view == "front" and seed == 1:  # first draw: a profile
                return raw_generated("side", noise=self.noise)
            return img

    res = make_pair("x", Profile(), "southern_cross", seed=1)
    assert res.seeds["front"] != 1 and res.metrics["front"]["candidates_tried"] >= 2


def test_a_big_drawn_gap_is_allowed_but_a_mid_size_hole_is_not():
    base = good_sprite(SC)
    big = base.copy()
    big[48:60, 40:50] = 0  # 120 px gap ringed by sprite: a tail loop
    assert "holes" not in words(check_sprite(big, SC))
    mid = base.copy()
    mid[48:54, 40:46] = 0  # 36 px
    assert "1 holes" in words(check_sprite(mid, SC))


def test_a_tall_contact_shadow_round_the_feet_is_removed():
    from asset_forge.sprites.post import remove_background

    img = native_creature().copy()
    img[112:126, 56:76] = (121, 117, 127)  # grey patch under the feet, taller than a flat shadow
    img[100:104, 20:26] = (121, 118, 126)  # and a scrap of the same grey elsewhere
    rgba = remove_background(img)
    assert rgba[118, 66, 3] == 0 and rgba[102, 22, 3] == 0
    assert rgba[70, 60, 3] == 255
