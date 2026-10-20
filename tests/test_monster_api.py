"""Monsters through the app's API (Blender mocked): the Step 1 limb gate on a generated model,
the proposed limb chains, and Build skeleton with the confirmed chains."""

from __future__ import annotations

import json

import numpy as np
from glb_factory import write_mesh_glb
from test_skeleton_api import client, fake_rig, finish, new_asset  # noqa: F401
from test_skeleton_api import put_clean as put_cube

from asset_forge import api
from asset_forge.generators import GenResult

FIX = "tests/fixtures/monsters/{}.npz"


def put_monster(settings, aid, name="triposg_spider"):
    d = np.load(FIX.format(name))
    out = settings.library_dir / aid / "clean"
    out.mkdir(parents=True, exist_ok=True)
    write_mesh_glb(out / "clean.glb", d["v"], d["f"].reshape(-1, 3))


def test_the_proposal_finds_eight_legs_and_is_kept(client, settings):  # noqa: F811
    aid = new_asset(client, "monster")
    put_monster(settings, aid)
    r = client.get(f"/api/assets/{aid}/skeleton/limbs")
    assert r.status_code == 200
    p = r.json()
    assert p["counts"]["legs"] == 8 and not p["confirmed"]
    assert all(len(lb["joints"]) == 4 for lb in p["limbs"]) and len(p["spine"]) == 4
    assert (settings.library_dir / aid / "skeleton" / "proposal.json").is_file()
    assert client.get(f"/api/assets/{aid}/skeleton/limbs").json() == p  # no re-proposal


def test_build_skeleton_needs_the_confirmed_limbs(client, settings):  # noqa: F811
    aid = new_asset(client, "monster")
    put_cube(settings, aid)
    r = client.post(f"/api/assets/{aid}/skeleton")
    assert r.status_code == 400 and "limb markers" in r.json()["detail"]
    r = client.post(f"/api/assets/{aid}/skeleton", json={"spine": [[0, 0, 1]] * 4, "limbs": []})
    assert r.status_code == 400 and "at least one limb" in r.json()["detail"]


def test_confirmed_limbs_are_kept_and_passed_to_the_rig(client, settings, monkeypatch):  # noqa: F811
    seen = {}

    def rig_spy(clean_glb, out_dir, asset_type, blender_exe, **kw):
        seen.update(kw, type=asset_type)
        return fake_rig(clean_glb, out_dir, asset_type, blender_exe)

    monkeypatch.setattr(api, "rig", rig_spy)
    aid = new_asset(client, "monster")
    put_monster(settings, aid)
    p = client.get(f"/api/assets/{aid}/skeleton/limbs").json()
    p["limbs"] = p["limbs"][1:]  # the user removed a limb
    p["limbs"][0]["joints"][3] = [0.5, -0.5, 0.0]  # and dragged a tip
    job = client.post(f"/api/assets/{aid}/skeleton", json=p).json()
    assert finish(client, job["id"])["state"] == "done"
    chain = json.loads(seen["chain"].read_text())
    assert seen["type"] == "monster" and len(chain["limbs"]) == 7
    assert chain["limbs"][0]["joints"][3] == [0.5, -0.5, 0.0]
    # that tip is now off the spider: the result names it so the page can mark it red
    assert client.get(f"/api/jobs/{job['id']}").json()["result"]["outside"] == [[0, 3]]
    again = client.get(f"/api/assets/{aid}/skeleton/limbs").json()
    assert again["confirmed"] and len(again["limbs"]) == 7
    fresh = client.get(f"/api/assets/{aid}/skeleton/limbs?fresh=1").json()
    assert not fresh["confirmed"] and len(fresh["limbs"]) == 8  # Start the limbs again


def test_step1_says_when_a_spider_has_the_wrong_number_of_legs(client, settings, monkeypatch):  # noqa: F811
    aid = new_asset(client, "monster")  # a picture asset with the words added (no drawer here)
    client.app.state.store.set_prompt(aid, "a spider-like monster with eight legs")
    d = np.load(FIX.format("hi3dgen_spider"))

    def run(image, out_dir, seed, progress):
        return GenResult(write_mesh_glb(out_dir / "raw.glb", d["v"], d["f"].reshape(-1, 3)),
                         1.0, 2.0, {})

    first = client.get("/api/menu").json()["generators"][0]["id"]
    monkeypatch.setattr(client.app.state.registry.get(first), "run", run)
    job = client.post(f"/api/assets/{aid}/generate", json={"generator": first}).json()
    res = finish(client, job["id"], timeout=60)["result"]
    a = res["anatomy"]
    assert a["ok"] is False and a["counts"]["legs"] == 10 and a["expected"] == {"legs": 8}
    assert "10 legs, not 8" in a["message"] and "only move bones" in a["message"]


def test_step1_has_nothing_to_say_without_numbers_in_the_words(client, settings):  # noqa: F811
    aid = new_asset(client, "humanoid")
    first = client.get("/api/menu").json()["generators"][0]["id"]
    job = client.post(f"/api/assets/{aid}/generate", json={"generator": first}).json()
    assert finish(client, job["id"])["result"]["anatomy"] is None
