"""Step 4 behind the app's API: Animate and Export on the GPU queue (animate() and
export_animated() mocked; Blender and Godot are not needed)."""

from __future__ import annotations

import pytest
from anim_factory import clips_json, write_anim_glb
from fastapi.testclient import TestClient
from test_skeleton_api import finish, new_asset

from asset_forge import api
from asset_forge.animate import NOT_YET, AnimFailed, AnimResult
from asset_forge.api import create_app
from asset_forge.export import ExportRefused


@pytest.fixture
def client(settings, fake_registry):
    app = create_app(settings, fake_registry)
    with TestClient(app) as c:
        yield c
    app.state.queue.shutdown()


def put_rig(settings, asset_id):
    d = settings.library_dir / asset_id / "skeleton"
    d.mkdir(parents=True, exist_ok=True)
    (d / "rigged.blend").write_bytes(b"BLENDER-fake")


def fake_animate(rigged_blend, out_dir, blender_exe, asset_type="humanoid", repo=None,
                 previews=None, timeout=900):
    out_dir.mkdir(parents=True, exist_ok=True)
    write_anim_glb(out_dir / "animated.glb")
    rep = clips_json()
    return AnimResult(out_dir, rep["template"], rep["clips"], 1.5, {"slide_cm": {}}, [])


def test_animate_runs_on_the_queue_and_serves_the_animated_file(client, settings, monkeypatch):
    seen = {}

    def spy(*a, **k):
        seen.update(k, blend=a[0])
        return fake_animate(*a, **k)

    monkeypatch.setattr(api, "animate", spy)
    aid = new_asset(client)
    put_rig(settings, aid)
    job = client.post(f"/api/assets/{aid}/animate").json()
    assert job["step"] == "animate"
    done = finish(client, job["id"])
    assert done["state"] == "done", done
    assert [c["name"] for c in done["result"]["clips"]][:3] == ["idle", "walk", "run"]
    assert seen["blend"].name == "rigged.blend" and seen["asset_type"] == "humanoid"
    asset = client.get(f"/api/assets/{aid}").json()
    assert asset["reached"] == "animate"
    assert client.get(f"/api/assets/{aid}/files/animate/animated.glb").status_code == 200


def test_animate_before_the_skeleton_says_what_to_do_first(client):
    aid = new_asset(client)
    r = client.post(f"/api/assets/{aid}/animate")
    assert r.status_code == 409 and "skeleton first" in r.json()["detail"]


def test_monsters_are_not_animated_yet_in_plain_words(client, settings):
    aid = new_asset(client, "monster")
    put_rig(settings, aid)
    r = client.post(f"/api/assets/{aid}/animate")
    assert r.status_code == 400 and r.json()["detail"] == NOT_YET


def test_an_unknown_model_is_a_404(client):
    assert client.post("/api/assets/a-20261020-000000-dead/animate").status_code == 404
    assert client.post("/api/assets/a-20261020-000000-dead/export").status_code == 404


def test_failed_animations_show_their_plain_words_on_the_job(client, settings, monkeypatch):
    def bad(*a, **k):
        raise AnimFailed("In walk, the LeftFoot slides 3.0 cm while it is on the ground.")

    monkeypatch.setattr(api, "animate", bad)
    aid = new_asset(client)
    put_rig(settings, aid)
    j = finish(client, client.post(f"/api/assets/{aid}/animate").json()["id"])
    assert j["state"] == "failed" and "slides 3.0 cm" in j["error"]


def test_export_before_animate_says_what_to_do_first(client):
    aid = new_asset(client)
    r = client.post(f"/api/assets/{aid}/export")
    assert r.status_code == 409 and "press Animate" in r.json()["detail"]


def test_export_runs_on_the_queue_and_writes_to_exports(client, settings, monkeypatch):
    seen = {}

    def fake_export(anim_dir, asset_id, asset_type, exports_dir=None, **k):
        seen.update(anim_dir=anim_dir, asset_type=asset_type, exports_dir=exports_dir)
        dest = exports_dir / asset_id
        dest.mkdir(parents=True)
        (dest / f"{asset_id}.glb").write_bytes(b"glb")
        return dest, {"measured": {"triangles": 10}, "problems": []}

    monkeypatch.setattr(api, "animate", fake_animate)
    monkeypatch.setattr(api, "export_animated", fake_export)
    aid = new_asset(client)
    put_rig(settings, aid)
    finish(client, client.post(f"/api/assets/{aid}/animate").json()["id"])
    job = client.post(f"/api/assets/{aid}/export").json()
    assert job["step"] == "export"
    done = finish(client, job["id"])
    assert done["state"] == "done", done
    assert done["result"]["files"] == [f"{aid}.glb"]
    assert seen["exports_dir"] == settings.library_dir.parent / "exports"
    assert seen["asset_type"] == "humanoid"


def test_a_refused_export_names_every_broken_limit(client, settings, monkeypatch):
    def refuse(*a, **k):
        raise ExportRefused(["It has 9,000 triangles; the limit is 8,000.",
                             "It uses 2 materials; the limit is 1."])

    monkeypatch.setattr(api, "animate", fake_animate)
    monkeypatch.setattr(api, "export_animated", refuse)
    aid = new_asset(client)
    put_rig(settings, aid)
    finish(client, client.post(f"/api/assets/{aid}/animate").json()["id"])
    j = finish(client, client.post(f"/api/assets/{aid}/export").json()["id"])
    assert j["state"] == "failed"
    assert "9,000 triangles" in j["error"] and "2 materials" in j["error"]
