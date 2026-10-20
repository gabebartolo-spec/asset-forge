"""Cut-out: the quick plain-background cut first, the cut-out model for busy backgrounds or when
asked. The model is replaced by a fake: no GPU."""

import io

import numpy as np
import pytest
from conftest import make_png
from fastapi.testclient import TestClient
from PIL import Image

from asset_forge.api import create_app
from asset_forge.cutout import CutoutError, Cutter, UnavailableCutter, needs_model
from asset_forge.matte import prepare_reference


class FakeCutter(Cutter):
    """Pretend model: keeps a centred box, drops the rest."""

    def __init__(self):
        self.calls = 0

    def cut(self, png: bytes) -> bytes:
        self.calls += 1
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        a = np.zeros((im.height, im.width), np.uint8)
        a[im.height // 4: 3 * im.height // 4, im.width // 4: 3 * im.width // 4] = 255
        im.putalpha(Image.fromarray(a))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def busy_picture() -> bytes:
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    noise[100:200, 100:200] = (200, 30, 30)  # the subject, on a busy background
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, "PNG")
    return buf.getvalue()


def client(settings, fake_registry, cutter):
    app = create_app(settings, fake_registry, cutter=cutter, release_writer=lambda: None)
    return app, TestClient(app)


def test_needs_model_only_when_the_quick_cut_left_no_single_subject():
    assert not needs_model(prepare_reference(make_png()))
    assert needs_model(prepare_reference(busy_picture()))


def test_a_plain_picture_never_touches_the_model(settings, fake_registry):
    fake = FakeCutter()
    app, c = client(settings, fake_registry, fake)
    with c:
        r = c.post("/api/assets", files={"image": ("a.png", make_png(), "image/png")},
                   data={"type": "humanoid"})
        assert r.status_code == 200 and fake.calls == 0
    app.state.queue.shutdown()


def test_a_busy_background_goes_to_the_model(settings, fake_registry):
    fake = FakeCutter()
    app, c = client(settings, fake_registry, fake)
    with c:
        r = c.post("/api/cutout", files={"image": ("b.png", busy_picture(), "image/png")})
        assert r.status_code == 200 and fake.calls == 1
        a = np.asarray(Image.open(io.BytesIO(r.content)).getchannel("A"))
        assert a[150, 150] == 255 and a[5, 5] == 0
    app.state.queue.shutdown()


def test_cut_again_forces_the_model_and_says_so_when_it_is_missing(settings, fake_registry):
    app, c = client(settings, fake_registry, UnavailableCutter())
    with c:
        files = {"image": ("a.png", make_png(), "image/png")}
        assert c.post("/api/cutout", files=files).status_code == 200  # the quick cut is enough
        r = c.post("/api/cutout", files=files, data={"model": "true"})
        assert r.status_code == 400 and "not set up" in r.json()["detail"]
        assert c.get("/api/menu").json()["cutout"]["available"] is False
    app.state.queue.shutdown()


def test_the_model_runs_inside_the_gpu_budget(settings, fake_registry):
    import asset_forge.gpu_lock as gl

    assert 0 < gl.vram_need("cutout:birefnet") < gl.DEFAULT_BUDGET_MB


def test_failed_model_run_is_plain_words(settings, fake_registry):
    class Broken(FakeCutter):
        def cut(self, png):
            raise CutoutError("The cut-out tool failed. Check the graphics card is free.")

    app, c = client(settings, fake_registry, Broken())
    with c:
        r = c.post("/api/cutout", files={"image": ("b.png", busy_picture(), "image/png")})
        assert r.status_code == 400 and "graphics card" in r.json()["detail"]
    app.state.queue.shutdown()


@pytest.mark.parametrize("data", [b"not a picture"])
def test_a_non_picture_is_refused_in_plain_words(settings, fake_registry, data):
    app, c = client(settings, fake_registry, FakeCutter())
    with c:
        r = c.post("/api/cutout", files={"image": ("x.png", data, "image/png")})
        assert r.status_code == 400 and "not a picture" in r.json()["detail"]
    app.state.queue.shutdown()
