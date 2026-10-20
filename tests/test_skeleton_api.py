"""The Skeleton step behind the app's one API call (rig() mocked; Blender is not needed)."""

from __future__ import annotations

import time

import pytest
from conftest import make_png
from fastapi.testclient import TestClient
from skin_factory import write_skinned_glb

from asset_forge import api, skeleton
from asset_forge.api import create_app


@pytest.fixture
def client(settings, fake_registry):
    app = create_app(settings, fake_registry)
    with TestClient(app) as c:
        yield c
    app.state.queue.shutdown()


def new_asset(client, type_="humanoid"):
    r = client.post("/api/assets", files={"image": ("r.png", make_png(), "image/png")},
                    data={"type": type_})
    return r.json()["id"]


def put_clean(settings, asset_id):
    d = settings.library_dir / asset_id / "clean"
    d.mkdir(parents=True, exist_ok=True)
    write_skinned_glb(d / "clean.glb")


def finish(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def fake_rig(clean_glb, out_dir, asset_type, blender_exe, template=None, repo=None, chain=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    write_skinned_glb(out_dir / "rigged.glb")
    write_skinned_glb(out_dir / "test_pose.glb")
    return skeleton.RigResult(out_dir, "humanoid", 23, "blender_automatic", 4, 2.0, [])


def test_skeleton_runs_on_the_queue_and_serves_its_files(client, settings, monkeypatch):
    monkeypatch.setattr(api, "rig", fake_rig)
    aid = new_asset(client)
    put_clean(settings, aid)
    job = client.post(f"/api/assets/{aid}/skeleton").json()
    done = finish(client, job["id"])
    assert done["state"] == "done" and done["result"]["bones"] == 23
    asset = client.get(f"/api/assets/{aid}").json()
    assert asset["reached"] == "skeleton"
    assert {"rigged.glb", "test_pose.glb"} <= set(asset["steps"]["skeleton"]["files"])
    assert client.get(f"/api/assets/{aid}/files/skeleton/test_pose.glb").status_code == 200


def test_skeleton_before_clean_says_what_to_do_first(client):
    aid = new_asset(client)
    r = client.post(f"/api/assets/{aid}/skeleton")
    assert r.status_code == 409 and "Clean up the model first" in r.json()["detail"]


def test_monster_skeleton_waits_for_the_confirmed_limbs_in_plain_words(client, settings):
    aid = new_asset(client, "monster")
    put_clean(settings, aid)
    r = client.post(f"/api/assets/{aid}/skeleton")
    assert r.status_code == 400 and "limb markers" in r.json()["detail"]


def test_a_rig_that_fails_its_gate_shows_the_plain_words_on_the_job(client, settings,
                                                                    monkeypatch):
    def bad(*a, **k):
        raise skeleton.RigFailed("Some parts of the model follow 8 bones at once; "
                                 "the limit is 4.")

    monkeypatch.setattr(api, "rig", bad)
    aid = new_asset(client)
    put_clean(settings, aid)
    j = finish(client, client.post(f"/api/assets/{aid}/skeleton").json()["id"])
    assert j["state"] == "failed" and "limit is 4" in j["error"]
