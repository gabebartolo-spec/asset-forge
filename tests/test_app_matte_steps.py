import io

import numpy as np
import pytest
from conftest import make_png
from PIL import Image

from asset_forge.matte import prepare_reference
from asset_forge.steps import clean_command


def alpha_of(img):
    return np.asarray(img.getchannel("A"))


def test_plain_background_is_cut_out_and_the_figure_stays():
    a = alpha_of(prepare_reference(make_png()))
    assert a[0, 0] == 0 and a[-1, -1] == 0 and a[100, 100] == 255


def test_a_hole_inside_the_figure_is_not_cut():
    im = Image.new("RGB", (200, 200), "white")
    px = im.load()
    for y in range(40, 160):
        for x in range(40, 160):
            px[x, y] = (200, 30, 30)
    for y in range(90, 110):
        for x in range(90, 110):
            px[x, y] = (255, 255, 255)  # a white eye inside the figure
    buf = io.BytesIO()
    im.save(buf, "PNG")
    a = alpha_of(prepare_reference(buf.getvalue()))
    assert a[100, 100] == 255 and a[5, 5] == 0


def test_big_pictures_are_shrunk_and_junk_is_refused():
    big = Image.new("RGBA", (3000, 1500), (0, 0, 0, 0))
    big.paste((10, 200, 10, 255), (500, 300, 1500, 1200))
    buf = io.BytesIO()
    big.save(buf, "PNG")
    assert max(prepare_reference(buf.getvalue()).size) == 1024
    with pytest.raises(ValueError, match="not a picture"):
        prepare_reference(b"hello")
    blank = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(blank, "PNG")
    with pytest.raises(ValueError, match="could not find the character"):
        prepare_reference(blank.getvalue())


def test_clean_hook_builds_the_documented_blender_command(tmp_path):
    cmd = clean_command("blender", tmp_path, tmp_path / "raw.glb", tmp_path / "clean",
                        "monster", tmp_path / "ref.png")
    clean_py = str(tmp_path / "blender" / "clean.py")
    assert cmd[:6] == ["blender", "-b", "--factory-startup", "-P", clean_py, "--"]
    assert cmd[6:] == [str(tmp_path / "raw.glb"), str(tmp_path / "clean"), "--type", "monster",
                       "--ref", str(tmp_path / "ref.png")]


def test_clean_hook_defaults_to_multiview_colour_when_models_are_given(tmp_path):
    models = tmp_path / "models"
    cmd = clean_command("blender", tmp_path, tmp_path / "raw.glb", tmp_path / "clean", "animal",
                        tmp_path / "ref.png", generator="hi3dgen", models_dir=models)
    tail = cmd[cmd.index("--ref") + 2:]
    assert tail == ["--generator", "hi3dgen",
                    "--mv-python", str(models / "envs" / "sdxl" / "Scripts" / "python.exe"),
                    "--mv-src", str(models / "src" / "mv_adapter"),
                    "--hf-home", str(models / "hf")]
