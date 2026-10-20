"""Method B colour (MV-Adapter): the reference layout the generator expects. Pure Python; the
generator itself is GPU-only and never runs in CI."""

import numpy as np

from asset_forge import multiview


def _figure(h=200, w=80, size=400):
    img = np.zeros((size, size, 4), np.uint8)
    y0, x0 = 150, 10  # off centre on purpose
    img[y0:y0 + h, x0:x0 + w] = (200, 30, 30, 255)
    return img


def test_reference_is_centred_on_grey_with_longest_side_at_090():
    out = multiview.prepare_reference(_figure(), size=768)
    assert out.shape == (768, 768, 3)
    fg = np.any(np.abs(out.astype(int) - 127) > 20, axis=2)
    ys, xs = np.nonzero(fg)
    assert abs((ys.max() - ys.min() + 1) - int(768 * 0.9)) <= 3  # longest side 0.9 x size
    assert abs((ys.min() + ys.max()) / 2 - 383.5) <= 2
    assert abs((xs.min() + xs.max()) / 2 - 383.5) <= 2
    assert tuple(out[0, 0]) == (127, 127, 127)  # MV-Adapter's 0.5 grey background


def test_wide_reference_scales_by_width():
    out = multiview.prepare_reference(_figure(h=40, w=300), size=768)
    fg = np.any(np.abs(out.astype(int) - 127) > 20, axis=2)
    xs = np.nonzero(fg)[1]
    assert abs((xs.max() - xs.min() + 1) - int(768 * 0.9)) <= 3


def test_generator_import_needs_no_gpu_stack():
    # the module is imported by the app; torch and diffusers load only inside run()
    assert "torch" not in multiview.__dict__
