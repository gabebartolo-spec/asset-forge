"""Step 2 behind the app: the clean call runs on the queue, reads report.json, and says in plain
words which limit broke. The Blender run is a fake (no Blender, no GPU)."""

from __future__ import annotations

import time

import pytest
from conftest import GOOD_REPORT, fake_cleaner, make_png
from fastapi.testclient import TestClient

from asset_forge.api import create_app
from asset_forge.draw import MockDrawer


def make_client(settings, registry, **kw):
    app = create_app(settings, registry, drawer=MockDrawer(), **kw)
    return app, TestClient(app)


@pytest.fixture
def log():
    return []


@pytest.fixture
def client(settings, fake_registry, log):
    app, c = make_client(settings, fake_registry, cleaner=fake_cleaner(log=log))
    with c:
        yield c
    app.state.queue.shutdown()


def finish(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def made(client, type_="humanoid"):
    aid = client.post("/api/assets", files={"image": ("r.png", make_png(), "image/png")},
                      data={"type": type_}).json()["id"]
    j = client.post(f"/api/assets/{aid}/generate", json={"generator": "triposg"}).json()
    assert finish(client, j["id"])["state"] == "done"
    return aid


def test_clean_before_make_is_a_plain_409(client):
    aid = client.post("/api/assets", files={"image": ("r.png", make_png(), "image/png")},
                      data={"type": "humanoid"}).json()["id"]
    r = client.post(f"/api/assets/{aid}/clean")
    assert r.status_code == 409 and "Make the 3D model first" in r.json()["detail"]
    assert client.post("/api/assets/a-20200101-000000-abcd/clean").status_code == 404


def test_clean_passes_and_serves_the_cleaned_model(client, log):
    aid = made(client)
    j = finish(client, client.post(f"/api/assets/{aid}/clean").json()["id"])
    assert j["state"] == "done"
    r = j["result"]
    assert r["passed"] and r["problems"] == [] and r["triangles"] == 7600
    assert r["texture"] == {"width": 1024, "height": 1024}
    cmd = log[0]
    assert cmd[cmd.index("--type") + 1] == "humanoid"
    assert cmd[cmd.index("--generator") + 1] == "triposg"  # the maker that was used
    assert cmd[cmd.index("--ref") + 1].endswith("input.png")
    a = client.get(f"/api/assets/{aid}").json()
    assert a["reached"] == "clean" and "clean.glb" in a["steps"]["clean"]["files"]
    assert a["timings"]["clean"] >= 0
    assert client.get(f"/api/assets/{aid}/files/clean/clean.glb").status_code == 200


@pytest.mark.parametrize("patch,word", [
    ({"triangles": 9000}, "9,000"),
    ({"texture": {"width": 2048, "height": 2048}}, "2048x2048"),
    ({"silhouette": {"threshold": 0.08, "side": 0.2}}, "side outline"),
])
def test_a_broken_limit_is_named_and_blocks_the_skeleton(settings, fake_registry, patch, word):
    app, c = make_client(settings, fake_registry,
                         cleaner=fake_cleaner({**GOOD_REPORT, **patch}))
    with c:
        aid = made(c)
        j = finish(c, c.post(f"/api/assets/{aid}/clean").json()["id"])
        r = j["result"]
        assert j["state"] == "done" and r["passed"] is False
        assert len(r["problems"]) == 1 and word in r["problems"][0]
        assert c.get(f"/api/assets/{aid}").json()["reached"] == "generate"
        s = c.post(f"/api/assets/{aid}/skeleton")  # no Next past a failed gate
        assert s.status_code == 409 and "Clean up" in s.json()["detail"]
    app.state.queue.shutdown()


def test_failed_colour_check_is_a_problem(settings, fake_registry):
    rep = {**GOOD_REPORT, "colour_route": {"region_gates": {"passed": False, "gates": [
        {"gate": "belly", "value": 0.4, "limit": "<= 0.2", "ok": False},
        {"gate": "tail", "value": 0.1, "limit": "<= 0.2", "ok": True}]}}}
    app, c = make_client(settings, fake_registry, cleaner=fake_cleaner(rep))
    with c:
        aid = made(c, "animal")
        r = finish(c, c.post(f"/api/assets/{aid}/clean").json()["id"])["result"]
        assert not r["passed"] and any("belly" in p for p in r["problems"])
        assert not any("tail" in p for p in r["problems"])
    app.state.queue.shutdown()


def test_a_blender_crash_says_press_redo_and_old_files_are_gone(settings, fake_registry):
    state = {"ok": True}

    def flaky(cmd):
        return (fake_cleaner() if state["ok"] else fake_cleaner(code=1))(cmd)

    app, c = make_client(settings, fake_registry, cleaner=flaky)
    with c:
        aid = made(c)
        assert finish(c, c.post(f"/api/assets/{aid}/clean").json()["id"])["result"]["passed"]
        state["ok"] = False
        j = finish(c, c.post(f"/api/assets/{aid}/clean").json()["id"])
        assert j["state"] == "failed" and "Press Redo" in j["error"]
        assert c.get(f"/api/assets/{aid}/files/clean/clean.glb").status_code == 404
    app.state.queue.shutdown()


def test_skeleton_still_needs_a_clean_model(client):
    aid = made(client)
    assert client.post(f"/api/assets/{aid}/skeleton").status_code == 409


def test_batch_stops_at_clean_and_reports_a_failed_gate(settings, fake_registry):
    app, c = make_client(settings, fake_registry,
                         cleaner=fake_cleaner({**GOOD_REPORT, "triangles": 9000}))
    with c:
        b = c.post("/api/batch", json={"items": [{"prompt": "a knight", "type": "humanoid"}]}
                   ).json()
        end = time.time() + 10
        while not b["finished"] and time.time() < end:
            time.sleep(0.05)
            b = c.get(f"/api/batch/{b['id']}").json()
        item = b["items"][0]
        assert item["state"] == "failed" and "9,000" in item["error"]
        card = c.get("/api/library").json()[0]
        assert card["reached"] == "generate" and card["thumb"]
        assert "skeleton" not in c.get(f"/api/assets/{card['id']}").json()["steps"]
    app.state.queue.shutdown()
