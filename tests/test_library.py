"""Library tab (cards, duplicate, trash/restore), step timings and the batch queue.
Generation and drawing are fakes: no GPU."""

from __future__ import annotations

import time

import pytest
from conftest import FakeGenerator, fake_cleaner, make_png
from fastapi.testclient import TestClient

from asset_forge.api import create_app
from asset_forge.draw import MockDrawer
from asset_forge.generators import Registry


@pytest.fixture
def client(settings, fake_registry):
    app = create_app(settings, fake_registry, drawer=MockDrawer(), cleaner=fake_cleaner())
    with TestClient(app) as c:
        yield c
    app.state.queue.shutdown()


def wait_job(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def wait_batch(client, batch, timeout=15):
    end = time.time() + timeout
    while not batch["finished"] and time.time() < end:
        time.sleep(0.05)
        batch = client.get(f"/api/batch/{batch['id']}").json()
    assert batch["finished"], "batch did not finish"
    return batch


def new_picture_asset(client, type_="humanoid"):
    return client.post("/api/assets", files={"image": ("r.png", make_png(), "image/png")},
                       data={"type": type_}).json()["id"]


def made_asset(client, type_="humanoid"):
    aid = new_picture_asset(client, type_)
    j = client.post(f"/api/assets/{aid}/generate", json={"generator": "hi3dgen"}).json()
    assert wait_job(client, j["id"])["state"] == "done"
    return aid


def test_card_shows_thumbnail_type_and_last_step(client):
    aid = made_asset(client)
    new = new_picture_asset(client, "animal")
    cards = {c["id"]: c for c in client.get("/api/library").json()}
    assert cards[aid]["thumb"] and cards[aid]["reached"] == "generate"
    assert cards[aid]["type"] == "humanoid" and cards[aid]["created"]
    assert cards[new]["reached"] is None and not cards[new]["busy"]


def test_timings_are_recorded_per_step(client):
    aid = made_asset(client)
    t = client.get(f"/api/assets/{aid}").json()["timings"]
    assert set(t) == {"generate"} and t["generate"] >= 0
    # the draw of a text asset is its own entry
    tid = client.post("/api/assets/from-text", json={"prompt": "a knight", "type": "humanoid"}
                      ).json()["id"]
    wait_job(client, client.post(f"/api/assets/{tid}/draw", json={}).json()["id"])
    assert "draw" in client.get(f"/api/assets/{tid}").json()["timings"]


def test_duplicate_copies_every_step_and_keeps_the_original(client, settings):
    aid = made_asset(client)
    r = client.post(f"/api/assets/{aid}/duplicate")
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != aid and new["copied_from"] == aid and new["reached"] == "generate"
    assert (settings.library_dir / new["id"] / "generate" / "raw.glb").is_file()
    assert (settings.library_dir / aid / "generate" / "raw.glb").is_file()
    assert len(client.get("/api/library").json()) == 2


def test_trash_moves_to_trash_and_restore_brings_it_back(client, settings):
    aid = made_asset(client)
    assert client.post(f"/api/assets/{aid}/trash").status_code == 200
    assert client.get("/api/library").json() == []
    assert [c["id"] for c in client.get("/api/library?trash=1").json()] == [aid]
    assert (settings.library_dir / "_trash" / aid / "generate" / "raw.glb").is_file()
    assert client.get(f"/api/assets/{aid}").status_code == 404
    assert client.post(f"/api/assets/{aid}/restore").status_code == 200
    assert [c["id"] for c in client.get("/api/library").json()] == [aid]
    assert client.get(f"/api/assets/{aid}").status_code == 200


def test_there_is_no_way_to_hard_delete(client):
    aid = made_asset(client)
    assert client.delete(f"/api/assets/{aid}").status_code in (404, 405)


def test_cannot_trash_or_copy_while_it_is_being_made(settings):
    slow = Registry([FakeGenerator("hi3dgen", "Hi3DGen", sleep=0.6)])
    app = create_app(settings, slow, drawer=MockDrawer(), cleaner=fake_cleaner())
    with TestClient(app) as c:
        aid = new_picture_asset(c)
        job = c.post(f"/api/assets/{aid}/generate", json={"generator": "hi3dgen"}).json()
        assert c.post(f"/api/assets/{aid}/trash").status_code == 409
        assert c.post(f"/api/assets/{aid}/duplicate").status_code == 409
        wait_job(c, job["id"])
        end = time.time() + 5  # "done" shows a moment before its result is on disk
        code = c.post(f"/api/assets/{aid}/trash").status_code
        while code == 409 and time.time() < end:
            time.sleep(0.02)
            code = c.post(f"/api/assets/{aid}/trash").status_code
        assert code == 200
    app.state.queue.shutdown()


def test_restore_unknown_and_bad_ids_are_plain_404s(client):
    assert client.post("/api/assets/a-20200101-000000-abcd/restore").status_code == 404
    assert client.post("/api/assets/x/restore").status_code == 404


def test_batch_of_three_runs_in_order_and_fills_the_library(client):
    r = client.post("/api/batch", json={"items": [
        {"prompt": "a knight", "type": "humanoid"},
        {"prompt": "a wolf", "type": "animal"},
        {"prompt": "a six-armed brute", "type": "monster"}]})
    assert r.status_code == 200
    b = r.json()
    assert len(b["items"]) == 3
    b = wait_batch(client, b)
    assert b["done"] == 3
    cards = {c["id"]: c for c in client.get("/api/library").json()}
    assert len(cards) == 3
    for it in b["items"]:
        c = cards[it["asset_id"]]
        # a batch runs Make and Clean up, then stops: no skeleton is ever queued (design 5.5)
        assert c["reached"] == "clean" and c["thumb"] and c["prompt"] == it["prompt"]
        assert set(c["timings"]) == {"draw", "generate", "clean"}
    assert [cards[i["asset_id"]]["type"] for i in b["items"]] == ["humanoid", "animal", "monster"]


def test_batch_progress_says_which_model_and_who_is_ahead(settings):
    slow = Registry([FakeGenerator("hi3dgen", "Hi3DGen", sleep=0.4)])
    app = create_app(settings, slow, drawer=MockDrawer(), cleaner=fake_cleaner())
    with TestClient(app) as c:
        b = c.post("/api/batch", json={"items": [
            {"prompt": "one", "type": "humanoid"}, {"prompt": "two", "type": "animal"}]}).json()
        time.sleep(0.2)
        view = c.get(f"/api/batch/{b['id']}").json()
        first, second = view["items"]
        assert first["state"] == "running" and first["message"].startswith("Model 1 of 2:")
        assert second["state"] in ("queued", "waiting") and second["ahead"] == 1
        wait_batch(c, view)
    app.state.queue.shutdown()


def test_a_failed_item_does_not_stop_the_rest(settings):
    gen = FakeGenerator("hi3dgen", "Hi3DGen", fail=True)
    app = create_app(settings, Registry([gen]), drawer=MockDrawer(), cleaner=fake_cleaner())
    with TestClient(app) as c:
        b = wait_batch(c, c.post("/api/batch", json={"items": [
            {"prompt": "a", "type": "humanoid"}, {"prompt": "b", "type": "humanoid"}]}).json())
        assert [i["state"] for i in b["items"]] == ["failed", "failed"]
        assert all("Press Redo" in i["error"] for i in b["items"])
        cards = c.get("/api/library").json()
        assert all(card["failed"] and card["thumb"] for card in cards)  # the picture is kept
    app.state.queue.shutdown()


@pytest.mark.parametrize("items", [
    [], [{"prompt": "  ", "type": "humanoid"}], [{"prompt": "x", "type": "dragon"}],
    [{"prompt": "x" * 700, "type": "humanoid"}], [{"prompt": "x", "type": "humanoid"}] * 21])
def test_batch_rejects_bad_input_before_creating_anything(client, items):
    assert client.post("/api/batch", json={"items": items}).status_code == 400
    assert client.get("/api/library").json() == []


def test_batch_says_so_when_drawing_is_not_ready(settings, fake_registry):
    app = create_app(settings, fake_registry)  # default drawer: unavailable
    with TestClient(app) as c:
        r = c.post("/api/batch", json={"items": [{"prompt": "x", "type": "humanoid"}]})
        assert r.status_code == 501 and "ready" in r.json()["detail"]
    app.state.queue.shutdown()
