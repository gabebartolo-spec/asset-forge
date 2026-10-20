"""Monsters, pure Python: the limb counter (Step 1 gate and Step 3 proposal), the words that set
an expected count, the bones built from confirmed limb chains, and the API around them.

Fixtures: tests/fixtures/monsters/*.npz are the Clean step's real outputs (8k triangles,
positions and triangles only) for the bake-off's "spider-like monster with eight legs" and
"six-armed brute" from Hi3DGen and TripoSG. The Hi3DGen spider came out with 10 legs, the
TripoSG one with 8; both brutes came out with 2 arms. Made by tools/skeleton/monster_fixtures.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from asset_forge import anatomy, skeleton
from asset_forge.skeleton import limbs
from asset_forge.skeleton.monster import MAX_LIMBS, ChainError, monster_bones, monster_pose
from asset_forge.skeleton.templates import MAX_BONES

FIX = Path(__file__).parent / "fixtures" / "monsters"


def load(name):
    d = np.load(FIX / f"{name}.npz")
    return d["v"].astype(float), d["f"].astype(np.int64)


@pytest.fixture(scope="module")
def proposals():
    return {n: limbs.propose(*load(n)) for n in
            ("hi3dgen_spider", "triposg_spider", "hi3dgen_brute", "triposg_brute")}


def boxes(specs):
    """A mesh made of boxes: (centre, size) pairs, overlapping where parts join."""
    unit = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)])
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    v, f = [], []
    for c, s in specs:
        base = len(v) * 8
        v.append(unit * np.asarray(s) + np.asarray(c))
        for a, b, cc, d in quads:
            f += [(base + a, base + b, base + cc), (base + a, base + cc, base + d)]
    return np.vstack(v), np.array(f)


def six_armed():
    """A blocky brute: two legs to the ground, a thick torso, a head, three arms a side."""
    parts = [((0, 0, 1.3), (0.7, 0.45, 0.8)), ((0, 0, 1.85), (0.3, 0.3, 0.3))]
    parts += [((x, 0, 0.45), (0.2, 0.2, 0.95)) for x in (-0.2, 0.2)]
    for z in (1.0, 1.3, 1.6):
        for s in (-1, 1):
            parts.append(((s * 0.75, 0, z), (0.8, 0.12, 0.12)))
    return boxes(parts)


# ---------------------------------------------------------------- the counter


def test_counts_ten_legs_on_the_hi3dgen_spider(proposals):
    assert proposals["hi3dgen_spider"].counts()["legs"] == 10


def test_counts_eight_legs_on_the_triposg_spider(proposals):
    # four of its legs are lifted off the ground; they still start where the others do
    assert proposals["triposg_spider"].counts()["legs"] == 8


@pytest.mark.parametrize("name", ["hi3dgen_brute", "triposg_brute"])
def test_the_six_armed_brutes_came_out_with_two_arms_and_two_legs(proposals, name):
    c = proposals[name].counts()
    assert (c["legs"], c["arms"]) == (2, 2)


def test_counts_six_arms_when_a_model_really_has_six():
    c = limbs.count_limbs(*six_armed())
    assert (c["legs"], c["arms"]) == (2, 6)


def test_a_limb_chain_runs_from_the_body_out_to_its_tip(proposals):
    p = proposals["triposg_spider"]
    for lb in p.limbs:
        j = np.array(lb.joints)
        assert j.shape == (4, 3)
        if lb.kind == "leg":
            assert j[0, 2] > j[-1, 2]  # a leg runs down from the body
    assert len(p.spine) == 4 and p.height > 0


@pytest.mark.parametrize("name", ["hi3dgen_spider", "triposg_spider", "hi3dgen_brute",
                                  "triposg_brute"])
def test_every_proposed_marker_sits_inside_the_body(proposals, name):
    # the triposg brute's hunched body line once started 7 cm outside its back
    assert limbs.outside_joints(*load(name), proposals[name].public()) == []


def test_a_marker_dragged_off_the_body_is_found(proposals):
    v, f = load("triposg_spider")
    chain = proposals["triposg_spider"].public()
    lo, hi = v.min(axis=0), v.max(axis=0)
    chain["limbs"][2]["joints"][3] = [float((lo[0] + hi[0]) / 2), float(lo[1]) - 0.3, float(lo[2])]
    chain["spine"][1] = [float(hi[0]) + 0.5, 0.0, float(hi[2])]
    assert limbs.outside_joints(v, f, chain) == [(-1, 1), (2, 3)]


# ---------------------------------------------------------------- the words


@pytest.mark.parametrize("words, want", [
    ("a spider-like monster with eight legs", {"legs": 8}),
    ("a giant spider", {"legs": 8}),
    ("a six-armed brute", {"arms": 6}),
    ("a four armed, two-legged demon", {"arms": 4, "legs": 2}),
    ("a 6 legged beetle", {"legs": 6}),
    ("a legless slime monster", {"legs": 0}),
    ("a knight armed with a sword", {}),
    ("an ogre holding a club in one arm", {}),
    ("", {}),
    (None, {}),
])
def test_only_the_words_set_an_expected_count(words, want):
    assert {k: v[0] for k, v in anatomy.expected_counts(words).items()} == want


def test_a_spider_with_ten_legs_is_flagged_in_plain_words():
    r = anatomy.judge({"legs": 10, "arms": 0}, anatomy.expected_counts("a giant spider"))
    assert not r["ok"]
    assert "10 legs, not 8" in r["message"]
    assert "only move bones" in r["message"] and "Re-roll" in r["message"]
    assert "cannot add or remove" not in r["message"]  # Step 3 does add and remove bones


def test_check_mesh_on_the_real_models(tmp_path, proposals, monkeypatch):
    # the real meshes, through the same counter the app calls after Step 1
    counts = {n: p.counts() for n, p in proposals.items()}
    spider_words = "a spider-like monster with eight legs"
    assert not anatomy.judge(counts["hi3dgen_spider"], anatomy.expected_counts(spider_words))["ok"]
    assert anatomy.judge(counts["triposg_spider"], anatomy.expected_counts(spider_words))["ok"]
    for brute in ("hi3dgen_brute", "triposg_brute"):
        r = anatomy.judge(counts[brute], anatomy.expected_counts("a six-armed brute"))
        assert not r["ok"] and "2 arms, not 6" in r["message"]


def test_check_mesh_reads_a_glb_and_skips_when_nothing_is_expected(tmp_path):
    from glb_factory import write_cube_glb

    cube = write_cube_glb(tmp_path / "c.glb")
    assert anatomy.check_mesh(cube, "a nice chair", "humanoid") is None
    r = anatomy.check_mesh(cube, "a spider", "monster")
    assert r is not None and not r["ok"] and r["expected"] == {"legs": 8}


# ---------------------------------------------------------------- bones from chains


def chain_of(p: limbs.Proposal) -> dict:
    return json.loads(json.dumps(p.public()))


def test_bones_from_confirmed_chains_fit_the_limits(proposals):
    for name, p in proposals.items():
        bones, joints, info = monster_bones(chain_of(p))
        assert len(bones) == 4 + 3 * len(p.limbs) <= MAX_BONES, name
        assert all(b.name in joints and b.tail in joints for b in bones)
        names = [b.name for b in bones]
        assert len(set(names)) == len(names)
        assert {i["kind"] for i in info} <= {"leg", "arm", "head", "tail"}
        assert sum(i["kind"] == "leg" for i in info) == p.counts()["legs"]
        parents = {b.name: b.parent for b in bones}
        assert all(parents[b] in names for b in names if parents[b])


def test_left_and_right_limbs_are_named_by_side(proposals):
    bones, joints, info = monster_bones(chain_of(proposals["triposg_spider"]))
    sides = [i["side"] for i in info if i["kind"] == "leg"]
    assert sides.count("L") == sides.count("R") == 4
    for i in info:
        x = joints[i["bones"][0]][0]
        assert (x > 0) == (i["side"] == "L") or i["side"] == "middle"


def test_an_edited_chain_is_checked_in_plain_words(proposals):
    good = chain_of(proposals["triposg_brute"])
    with pytest.raises(ChainError, match="at least one limb"):
        monster_bones({**good, "limbs": []})
    with pytest.raises(ChainError, match="4 markers"):
        monster_bones({**good, "limbs": [{"kind": "leg", "joints": [[0, 0, 0]]}]})
    with pytest.raises(ChainError, match="kind"):
        monster_bones({**good, "limbs": [{"kind": "wing", "joints": good["limbs"][0]["joints"]}]})
    too_many = [good["limbs"][0]] * (MAX_LIMBS + 1)
    with pytest.raises(ChainError, match="Remove some"):
        monster_bones({**good, "limbs": too_many})


def test_the_monster_test_pose_bends_every_joint_of_every_limb_about_30_degrees(proposals):
    bones, joints, info = monster_bones(chain_of(proposals["hi3dgen_spider"]))
    pose = monster_pose(info, joints)
    turn = {b: abs(deg) for b, _, deg in pose}
    for lb in info:
        n = 3 if lb["kind"] in ("leg", "arm") else 2
        assert all(turn.get(b, 0) >= 30 for b in lb["bones"][:n]), lb["name"]
    moved = set(turn)
    names = {b.name for b in bones}
    assert moved <= names
    for _, axis, _ in pose:
        assert abs(np.linalg.norm(axis) - 1) < 1e-6 or np.linalg.norm(axis) > 0


def test_a_monster_without_confirmed_limbs_is_not_rigged(tmp_path):
    with pytest.raises(skeleton.RigFailed, match="limb markers"):
        skeleton.rig(tmp_path / "clean.glb", tmp_path / "out", "monster", "blender.exe")


def test_rig_command_passes_the_chain(tmp_path):
    cmd = skeleton.rig_command("b.exe", tmp_path, tmp_path / "c.glb", tmp_path / "o", "monster",
                               chain=tmp_path / "chain.json")
    assert cmd[-2:] == ["--chain", str(tmp_path / "chain.json")]
