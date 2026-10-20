import numpy as np
import pytest
from PIL import Image

from asset_forge.sprites import SpriteFailed, check_back_view, check_sprite, export_pair, make_pair
from asset_forge.sprites.post import OUTLINE_COLOUR, bbox
from asset_forge.sprites.presets import BACK_IOU_MAX, get_preset
from asset_forge.sprites.qa import back_overlap

from .fixtures import FakeDrawer, good_sprite

SC, GBA = get_preset("southern_cross"), get_preset("gba")


def words(problems):
    return " | ".join(problems)


@pytest.mark.parametrize("preset", [SC, GBA])
def test_good_sprite_passes(preset):
    assert check_sprite(good_sprite(preset), preset) == []


def test_unoutlined_edge_pixel_fails():
    s = good_sprite(SC)
    x0, y0, x1, y1 = bbox(s)
    s[y0, (x0 + x1) // 2] = (250, 250, 200, 255)
    assert "no dark outline" in words(check_sprite(s, SC))


def test_stray_pixel_fails():
    s = good_sprite(SC)
    s[8, 8] = (*OUTLINE_COLOUR, 255)
    assert "stray" in words(check_sprite(s, SC))


def test_hole_fails():
    s = good_sprite(SC)
    s[50:52, 48:50] = 0
    assert "hole" in words(check_sprite(s, SC))


def test_soft_edge_fails():
    s = good_sprite(SC)
    s[0:3, 0:3, 3] = 120
    assert "semi-transparent" in words(check_sprite(s, SC))


def test_too_close_to_the_edge_fails():
    s = good_sprite(SC)
    s = np.roll(s, -(bbox(s)[1] - 1), axis=0)  # top of the sprite now 1 px from the edge
    assert "closer than 2 px" in words(check_sprite(s, SC))


def test_leftover_background_fails():
    s = good_sprite(SC)
    s[...] = (240, 240, 240, 255)
    assert "background was not removed" in words(check_sprite(s, SC))


def test_too_many_colours_fails_for_gba():
    s = good_sprite(GBA)
    solid = np.argwhere(s[..., 3] > 0)
    for i, (y, x) in enumerate(solid[: 40 * 2 : 2]):
        s[y, x, :3] = (10 + i * 5, 200 - i * 3, 50 + i * 4)
    assert "colours" in words(check_sprite(s, GBA))


def test_tiny_and_empty_and_wrong_size_fail():
    tiny = np.zeros((SC.art_size, SC.art_size, 4), np.uint8)
    tiny[40:46, 40:46] = (*OUTLINE_COLOUR, 255)
    assert "too small" in words(check_sprite(tiny, SC))
    assert "empty" in words(check_sprite(np.zeros((SC.art_size, SC.art_size, 4), np.uint8), SC))
    assert "needs 80x80" in words(check_sprite(np.zeros((64, 64, 4), np.uint8), SC))


def test_back_that_copies_the_front_or_its_mirror_is_rejected():
    front = good_sprite(SC, "front")
    assert "same outline" in words(check_back_view(front, front.copy())[0])
    assert "same outline" in words(check_back_view(front, front[:, ::-1].copy())[0])


def test_a_real_back_view_passes_and_reports_its_overlap():
    problems, metrics = check_back_view(good_sprite(SC, "front"), good_sprite(SC, "back"))
    assert problems == [] and max(metrics.values()) < BACK_IOU_MAX
    assert back_overlap(good_sprite(SC, "front"), good_sprite(SC, "front"))["iou_front"] == 1.0


def test_pair_from_fake_drawer_exports_southern_cross_layout(tmp_path):
    res = make_pair("a small fire lizard creature", FakeDrawer(), "southern_cross", seed=5)
    files = export_pair(res, "FireLizard", tmp_path)
    front, back = (Image.open(f) for f in files)
    assert front.size == (160, 160) and back.size == (160, 160)  # D-023
    assert files[0].parent.name == "Front" and files[1].parent.name == "Back"
    assert files[0].name == "FIRELIZARD.png" and files[1].name == "FIRELIZARD.png"
    assert front.mode == "RGBA" and front.getpixel((0, 0))[3] == 0


def test_gba_export_is_indexed_16_colours_with_transparent_zero(tmp_path):
    res = make_pair("a small fire lizard creature", FakeDrawer(), "gba", seed=5)
    files = export_pair(res, "FireLizard", tmp_path)
    for f in files:
        img = Image.open(f)
        assert img.mode == "P" and img.size == (64, 64)
        assert img.info["transparency"] == 0 or img.info["transparency"][0] == 0
        assert max(img.getdata()) <= 15 and len(img.getpalette()) // 3 <= 16
        assert img.getpixel((0, 0)) == 0


def test_lazy_back_that_copies_the_front_is_never_exported(tmp_path):
    drawer = FakeDrawer(back_like_front=True)
    with pytest.raises(SpriteFailed) as e:
        make_pair("a small fire lizard creature", drawer, "southern_cross", seed=1)
    assert e.value.view == "pair" and "Re-roll" in str(e.value) and "same outline" in str(e.value)
    assert len(drawer.calls) == 6  # two draw calls of three sheets, then it gave up
    assert list(tmp_path.iterdir()) == []


def test_export_refuses_a_pair_that_fails_qa(tmp_path):
    res = make_pair("x", FakeDrawer(), "southern_cross", seed=1)
    res.back = res.front.copy()
    with pytest.raises(SpriteFailed):
        export_pair(res, "Bad", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_same_seed_same_pixels():
    a = make_pair("x", FakeDrawer(), "southern_cross", seed=3)
    b = make_pair("x", FakeDrawer(), "southern_cross", seed=3)
    assert np.array_equal(a.front, b.front) and np.array_equal(a.back, b.back)


def test_a_second_body_fails():
    from asset_forge.sprites.post import add_outline

    s = np.zeros((SC.art_size, SC.art_size, 4), np.uint8)
    s[8:30, 8:30] = (200, 90, 40, 255)
    s[60:84, 60:84] = (200, 90, 40, 255)  # two equal bodies far apart
    assert "more than one separate body" in words(check_sprite(add_outline(s), SC))
