"""Step 1 text path: Expand my idea on the GPU queue, the draw interface, text-only assets.
Everything is mocked: no GPU, no model."""

import io
import time

import pytest
from conftest import make_png
from fastapi.testclient import TestClient
from PIL import Image

from asset_forge import prompts
from asset_forge.api import create_app
from asset_forge.draw import UNAVAILABLE_NOTE, MockDrawer, UnavailableDrawer
from asset_forge.generators import GeneratorError
from asset_forge.prompts import llm


class Writer:
    def __init__(self):
        self.calls = []

    def __call__(self, idea, asset_type, seed):
        self.calls.append((idea, asset_type, seed))
        return f"A {idea} ({asset_type}, v{seed})"


@pytest.fixture
def parts(settings, fake_registry):
    writer, drawer, released = Writer(), MockDrawer(), []
    app = create_app(settings, fake_registry, expander=writer, drawer=drawer,
                     release_writer=lambda: released.append(1))
    with TestClient(app) as c:
        yield c, writer, drawer, released
    app.state.queue.shutdown()


def finish(c, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_expand_runs_on_the_queue_and_returns_the_prompt(parts):
    c, writer, _, _ = parts
    body = {"idea": "  six-armed   brute ", "type": "monster"}
    j = finish(c, c.post("/api/expand", json=body).json()["id"])
    assert j["state"] == "done" and j["result"]["prompt"] == "A six-armed brute (monster, vNone)"
    assert writer.calls == [("six-armed brute", "monster", None)]


def test_reroll_sends_a_seed_and_first_try_does_not(parts):
    c, writer, _, _ = parts
    finish(c, c.post("/api/expand", json={"idea": "fox", "type": "animal"}).json()["id"])
    again = {"idea": "fox", "type": "animal", "variation": 3}
    finish(c, c.post("/api/expand", json=again).json()["id"])
    assert [w[2] for w in writer.calls] == [None, 3]


def test_expand_takes_the_gpu_lock(parts, settings):
    c, _, _, _ = parts
    settings.lock_dir.mkdir(parents=True)  # another job holds the card
    (settings.lock_dir / "owner.txt").write_text("comfyui pid=1\n")
    jid = c.post("/api/expand", json={"idea": "fox", "type": "animal"}).json()["id"]
    time.sleep(1.3)
    j = c.get(f"/api/jobs/{jid}").json()
    assert j["state"] == "waiting" and "graphics card" in j["message"]
    (settings.lock_dir / "owner.txt").unlink()
    settings.lock_dir.rmdir()
    assert finish(c, jid, 10)["state"] == "done"


def test_expand_rejects_empty_and_unknown_type_in_plain_words(parts):
    c, *_ = parts
    r = c.post("/api/expand", json={"idea": "   ", "type": "monster"})
    assert r.status_code == 400 and "few words" in r.json()["detail"]
    r = c.post("/api/expand", json={"idea": "fox", "type": "dragon"})
    assert r.status_code == 400 and "Humanoid" in r.json()["detail"]
    r = c.post("/api/expand", json={"idea": "x" * 700, "type": "monster"})
    assert r.status_code == 400


def test_expand_failure_is_plain(settings, fake_registry):
    def boom(*_):
        raise GeneratorError("The idea writer could not run. Type the full description yourself.")

    app = create_app(settings, fake_registry, expander=boom, drawer=MockDrawer())
    with TestClient(app) as c:
        j = finish(c, c.post("/api/expand", json={"idea": "fox", "type": "animal"}).json()["id"])
        assert j["state"] == "failed" and "Type the full description" in j["error"]
    app.state.queue.shutdown()


def test_real_expander_maps_a_missing_model_to_plain_words(monkeypatch):
    from asset_forge.api import real_expander

    def missing(*a, **k):
        raise prompts.PromptGenError("Create models/envs/promptgen with uv")

    monkeypatch.setattr(llm, "generate", missing)
    with pytest.raises(GeneratorError) as e:
        real_expander("fox", "animal", None)
    assert "uv" not in str(e.value) and "Type the full description" in str(e.value)


def test_seed_only_reaches_the_model_on_a_reroll(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "generate", lambda s, i, t, **kw: seen.append(kw) or "A fox.")
    prompts.expand("fox", "animal")
    prompts.expand("fox", "animal", seed=4)
    assert seen == [{}, {"seed": 4}]


def test_menu_says_whether_drawing_from_text_is_there(parts, settings, fake_registry):
    c, *_ = parts
    assert c.get("/api/menu").json()["text_draw"]["available"] is True
    app = create_app(settings, fake_registry, expander=Writer())  # real default: not yet
    with TestClient(app) as c2:
        td = c2.get("/api/menu").json()["text_draw"]
    app.state.queue.shutdown()
    assert td == {"available": False, "note": UNAVAILABLE_NOTE}
    assert "isn't ready yet" in td["note"]


def test_text_only_without_a_drawer_is_plain_501_not_a_crash(settings, fake_registry):
    app = create_app(settings, fake_registry, expander=Writer(), drawer=UnavailableDrawer())
    with TestClient(app) as c:
        r = c.post("/api/assets/from-text", json={"prompt": "a fox", "type": "animal"})
        assert r.status_code == 501 and "isn't ready yet" in r.json()["detail"]
        r = c.post("/api/assets/a-20260101-000000-abcd/draw", json={})
        assert r.status_code == 501
    app.state.queue.shutdown()


def test_text_only_flow_draw_reroll_then_make_3d(parts):
    c, _, drawer, released = parts
    a = c.post("/api/assets/from-text", json={"prompt": "a green ogre", "type": "monster"}).json()
    assert a["prompt"] == "a green ogre"
    # no picture yet: the 3D run is refused in plain words
    r = c.post(f"/api/assets/{a['id']}/generate", json={"generator": "hi3dgen"})
    assert r.status_code == 400 and "Draw the picture first" in r.json()["detail"]
    j1 = finish(c, c.post(f"/api/assets/{a['id']}/draw", json={"seed": 1}).json()["id"])
    assert j1["state"] == "done" and j1["result"]["seed"] == 1
    first = c.get(f"/api/assets/{a['id']}/files/generate/input.png").content
    j2 = finish(c, c.post(f"/api/assets/{a['id']}/draw", json={"seed": 2}).json()["id"])
    second = c.get(f"/api/assets/{a['id']}/files/generate/input.png").content
    assert j2["state"] == "done" and first != second  # re-roll changes the picture
    assert [d[2] for d in drawer.calls] == [1, 2]
    assert drawer.calls[0][:2] == ("a green ogre", "monster")
    body = {"generator": "hi3dgen"}
    g = finish(c, c.post(f"/api/assets/{a['id']}/generate", json=body).json()["id"])
    assert g["state"] == "done" and g["result"]["mesh"] == "raw.glb"
    assert len(released) == 3  # idea writer freed before each draw and the 3D run


def test_draw_can_change_the_words_and_rejects_empty(parts):
    c, *_ = parts
    a = c.post("/api/assets/from-text", json={"prompt": "a fox", "type": "animal"}).json()
    finish(c, c.post(f"/api/assets/{a['id']}/draw", json={"prompt": " a red   fox "}).json()["id"])
    assert c.get(f"/api/assets/{a['id']}").json()["prompt"] == "a red fox"
    blank = c.post("/api/assets/from-text", json={"prompt": " ", "type": "animal"})
    assert blank.status_code == 400
    assert c.post("/api/assets/from-text", json={"prompt": "x", "type": "cat"}).status_code == 400
    assert c.post("/api/assets/a-20260101-000000-abcd/draw", json={}).status_code == 404


def test_a_bad_drawing_fails_in_plain_words(settings, fake_registry):
    class Blank(MockDrawer):
        def draw(self, *a):
            b = io.BytesIO()
            Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(b, "PNG")
            return b.getvalue()

    app = create_app(settings, fake_registry, expander=Writer(), drawer=Blank(),
                     release_writer=lambda: None)
    with TestClient(app) as c:
        a = c.post("/api/assets/from-text", json={"prompt": "a fox", "type": "animal"}).json()
        j = finish(c, c.post(f"/api/assets/{a['id']}/draw", json={}).json()["id"])
        assert j["state"] == "failed" and "Draw another" in j["error"]
    app.state.queue.shutdown()


def test_picture_upload_path_unchanged(parts):
    c, *_ = parts
    files = {"image": ("r.png", make_png(), "image/png")}
    a = c.post("/api/assets", files=files, data={"type": "humanoid"}).json()
    body = {"generator": "hi3dgen"}
    g = finish(c, c.post(f"/api/assets/{a['id']}/generate", json=body).json()["id"])
    assert g["state"] == "done"


def test_a_draw_with_several_creatures_is_drawn_again_with_the_next_seed(settings, fake_registry):
    from pathlib import Path

    tiled = (Path(__file__).parent / "fixtures" / "multi_fox_ref.png").read_bytes()

    class Tiled(MockDrawer):
        def draw(self, prompt, asset_type, seed, progress):  # noqa: ANN001
            png = super().draw(prompt, asset_type, seed, progress)
            return tiled if seed == 5 else png  # the first seed comes out as a tiled pattern

    drawer = Tiled()
    app = create_app(settings, fake_registry, expander=Writer(), drawer=drawer,
                     release_writer=lambda: None)
    with TestClient(app) as c:
        a = c.post("/api/assets/from-text", json={"prompt": "a fox", "type": "animal"}).json()
        j = finish(c, c.post(f"/api/assets/{a['id']}/draw", json={"seed": 5}).json()["id"])
        assert j["state"] == "done" and j["result"]["seed"] == 6
        assert [x[2] for x in drawer.calls] == [5, 6]
    app.state.queue.shutdown()

