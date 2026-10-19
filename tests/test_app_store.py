import json

import pytest
from conftest import make_png

from asset_forge.store import NotFound, Store


def test_create_asset_writes_the_library_layout(tmp_path):
    s = Store(tmp_path / "lib")
    a = s.create_asset("humanoid", make_png())
    d = tmp_path / "lib" / a["id"]
    assert (d / "asset.json").exists()
    assert (d / "generate" / "input.png").read_bytes() == make_png()
    assert json.loads((d / "asset.json").read_text())["type"] == "humanoid"


def test_unknown_type_is_refused_in_plain_words(tmp_path):
    with pytest.raises(ValueError, match="Humanoid, Monster or Animal"):
        Store(tmp_path).create_asset("dragon", b"x")


def test_settings_status_result_round_trip_and_listing(tmp_path):
    s = Store(tmp_path)
    a = s.create_asset("animal", make_png())
    s.write_settings(a["id"], "generate", {"generator": "hi3dgen", "seed": 7})
    s.write_status(a["id"], "generate", {"state": "done"})
    s.write_result(a["id"], "generate", {"mesh": "raw.glb"})
    s.mark_reached(a["id"], "generate")
    got = s.get_asset(a["id"])
    assert got["reached"] == "generate"
    assert got["steps"]["generate"]["settings"]["seed"] == 7
    assert [x["id"] for x in s.list_assets()] == [a["id"]]


@pytest.mark.parametrize("bad", ["../x", "a-1", "..", "a-20260101-000000-zzzz"])
def test_bad_ids_are_not_found(tmp_path, bad):
    with pytest.raises(NotFound):
        Store(tmp_path).asset_dir(bad)


def test_file_path_blocks_traversal(tmp_path):
    s = Store(tmp_path)
    a = s.create_asset("monster", make_png())
    assert s.file_path(a["id"], "generate", "input.png").exists()
    for name in ("../asset.json", "..\\asset.json", ".hidden", "missing.glb"):
        with pytest.raises(NotFound):
            s.file_path(a["id"], "generate", name)
    with pytest.raises(NotFound):
        s.file_path(a["id"], "bogus", "input.png")


def test_unfinished_jobs_fail_after_a_restart(tmp_path):
    s = Store(tmp_path)
    a = s.create_asset("monster", make_png())
    s.write_status(a["id"], "generate", {"state": "running", "message": "x"})
    assert s.fail_unfinished() == 1
    st = s.get_asset(a["id"])["steps"]["generate"]["status"]
    assert st["state"] == "failed" and "Redo" in st["error"]
