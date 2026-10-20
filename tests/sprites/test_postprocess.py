import numpy as np
import pytest
from PIL import Image

from asset_forge.sprites.grid import FALLBACK_PITCH, GridInfo, detect_grid, downsample_on_grid
from asset_forge.sprites.post import (
    add_outline,
    bbox,
    edge_pixels,
    fill_holes,
    fit_to_canvas,
    is_outline,
    process,
    reduce_palette,
    remove_background,
    remove_strays,
)
from asset_forge.sprites.presets import OUTLINE_COLOUR, get_preset

from .fixtures import good_sprite, native_creature, raw_generated

SC, GBA = get_preset("southern_cross"), get_preset("gba")


@pytest.mark.parametrize("pitch", [4, 6, 8, 12])
def test_detects_the_true_pixel_grid(pitch):
    rgb = np.asarray(raw_generated(pitch=pitch))
    info = detect_grid(rgb)
    assert info.found and info.pitch == pitch and info.confidence > 0.5


def test_detects_grid_through_noise():
    info = detect_grid(np.asarray(raw_generated(pitch=8, noise=10)))
    assert info.found and info.pitch == 8


def test_grid_phase_offset_is_found_and_native_pixels_recovered_exactly():
    native = native_creature()
    big = np.repeat(np.repeat(native, 8, axis=0), 8, axis=1)
    shifted = np.pad(big, ((3, 0), (5, 0), (0, 0)), constant_values=255)  # 3 down, 5 right
    info = detect_grid(shifted)
    assert (info.pitch, info.phase_x, info.phase_y) == (8, 5, 3)
    got = downsample_on_grid(shifted, info)
    assert np.array_equal(got[:127, :127], native[:127, :127])  # no smoothing, no new colours


def test_no_grid_in_a_smooth_image_falls_back_and_says_so():
    yy, xx = np.mgrid[0:256, 0:256]
    smooth = np.dstack([xx, yy, (xx + yy) // 2]).astype(np.uint8)
    info = detect_grid(smooth)
    assert not info.found and info.pitch == FALLBACK_PITCH


def test_downsample_of_a_noisy_image_returns_the_underlying_pixels():
    rgb = np.asarray(raw_generated(noise=12))
    got = downsample_on_grid(rgb, GridInfo(8, 0, 0, 1.0, True))
    off = np.abs(got.astype(int) - native_creature().astype(int))
    assert (off.max(axis=2) <= 13).mean() > 0.99  # each cell is its own pixel, not a blur


def test_background_removed_only_where_connected_to_the_border():
    rgba = remove_background(native_creature())
    assert rgba[0, 0, 3] == 0 and rgba[70, 60, 3] == 255
    ring = native_creature().copy()
    ring[60:64, 60:64] = 255  # white pocket inside the body, not connected to the border
    assert remove_background(ring)[62, 62, 3] == 255


def test_strays_removed_but_body_kept():
    s = good_sprite(SC)
    s[5, 5] = (*OUTLINE_COLOUR, 255)
    s[5, 7:9] = (*OUTLINE_COLOUR, 255)
    cleaned = remove_strays(s)
    assert cleaned[5, 5, 3] == 0 and cleaned[5, 7, 3] == 0
    assert cleaned[bbox(s)[1] + 10, 48, 3] == s[bbox(s)[1] + 10, 48, 3]


def test_holes_filled_with_the_surrounding_colour():
    s = good_sprite(SC)
    y, x = 50, 48
    s[y : y + 2, x : x + 2] = 0
    assert s[y, x, 3] == 0
    filled = fill_holes(s)
    assert (filled[..., 3] > 0)[y : y + 2, x : x + 2].all()


def test_fit_leaves_room_and_centres():
    out = fit_to_canvas(np.dstack([native_creature(), np.full((128, 128), 255, np.uint8)]), 96)
    x0, y0, x1, y1 = bbox(out)
    assert out.shape == (96, 96, 4) and min(x0, y0, 96 - x1, 96 - y1) >= 3


def test_palette_reduced_to_limit_without_dithering():
    rng = np.random.default_rng(3)
    s = np.dstack([rng.integers(0, 256, (32, 32, 3)), np.full((32, 32), 255)]).astype(np.uint8)
    r = reduce_palette(s, 14)
    assert len(np.unique(r[..., :3].reshape(-1, 3), axis=0)) <= 14
    assert (r[..., 3] == 255).all()


def test_outline_added_repaired_and_not_doubled():
    body = np.zeros((20, 20, 4), np.uint8)
    body[5:15, 5:15] = (230, 200, 120, 255)
    out = add_outline(body)
    assert not (edge_pixels(out) & ~is_outline(out)).any()
    assert out[4, 8, 3] == 255 and (out[4, 8, :3] == OUTLINE_COLOUR).all()
    again = add_outline(out)
    assert np.array_equal(again, out)  # an outlined sprite gets no second ring
    dark = body.copy()
    dark[5, 5:15] = (10, 10, 10, 255)  # model-drawn dark edge on top: repaired, not ringed
    fixed = add_outline(dark)
    assert fixed[4, 8, 3] == 0 and (fixed[5, 8, :3] == OUTLINE_COLOUR).all()


@pytest.mark.parametrize("preset", [SC, GBA])
def test_process_end_to_end_is_exact_size_and_deterministic(preset):
    raw = raw_generated(noise=8)
    a, meta = process(raw, preset)
    b, _ = process(raw, preset)
    assert a.shape == (preset.art_size, preset.art_size, 4) and np.array_equal(a, b)
    assert meta["grid_pitch"] == 8 and meta["grid_found"]
    assert set(np.unique(a[..., 3])) <= {0, 255}
    assert len(np.unique(a[a[..., 3] > 0][:, :3], axis=0)) <= preset.max_colours


def test_process_accepts_any_pil_mode():
    rgba_img = raw_generated().convert("RGBA")
    assert isinstance(rgba_img, Image.Image)
    sprite, _ = process(rgba_img, SC)
    assert sprite.shape == (SC.art_size, SC.art_size, 4)


def test_large_enclosed_background_pocket_is_removed_but_small_holes_filled():
    img = native_creature().copy()
    img[60:80, 56:66] = 255  # 200 px white pocket inside the body (curled tail)
    rgba = remove_background(img)
    assert rgba[70, 60, 3] == 0
    s = good_sprite(SC)
    s[50:52, 48:50] = 0
    assert fill_holes(s)[50, 48, 3] == 255
    big = good_sprite(SC)
    big[45:60, 45:55] = 0  # large enclosed gap: left for the QA to fail, not painted over
    assert fill_holes(big)[50, 50, 3] == 0


def test_flat_grey_ground_shadow_is_removed_but_the_body_stays():
    img = native_creature().copy()
    yy, xx = np.mgrid[0:128, 0:128]
    shadow = ((yy - 112) / 5.0) ** 2 + ((xx - 60) / 30.0) ** 2 <= 1
    img[shadow & (img.sum(axis=2) == 765)] = (150, 150, 150)
    rgba = remove_background(img)
    assert rgba[112, 60, 3] == 0 and rgba[70, 60, 3] == 255


def test_small_separate_pieces_are_dropped_but_an_equal_second_body_is_kept_for_the_qa():
    from asset_forge.sprites.post import keep_main_bodies

    s = np.zeros((64, 64, 4), np.uint8)
    s[10:40, 10:40] = 255  # 900 px body
    s[50:56, 50:56] = 255  # 36 px bit
    assert keep_main_bodies(s)[52, 52, 3] == 0
    s[44:62, 4:30] = 255  # second body, half the size
    assert keep_main_bodies(s)[50, 10, 3] == 255
