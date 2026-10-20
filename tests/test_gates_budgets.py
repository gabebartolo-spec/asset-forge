import pytest

from asset_forge.gates import Budget, check, check_file

GOOD = {"triangles": 7900, "materials": 1, "texture": {"width": 1024, "height": 1024},
        "silhouette": {"threshold": 0.08, "front": 0.03, "side": 0.05, "top": 0.07}}


def test_good_report_passes():
    assert check(GOOD, "humanoid") == []
    assert check(GOOD, "Monster") == []


def test_animal_budget_is_tighter():
    msgs = check(GOOD, "animal")
    assert any("7,900 against a limit of 2,000" in m for m in msgs)
    assert any("1024x1024" in m and "512x512" in m for m in msgs)


@pytest.mark.parametrize("patch,word", [
    ({"triangles": 8001}, "triangles"),
    ({"materials": 2}, "materials"),
    ({"texture": {"width": 2048, "height": 2048}}, "Texture"),
    ({"silhouette": {"threshold": 0.08, "side": 0.2}}, "side outline"),
    ({"bones": 65}, "bones"),
    ({"max_influences": 5}, "influences"),
])
def test_each_limit_is_named(patch, word):
    msgs = check({**GOOD, **patch}, "humanoid")
    assert len(msgs) == 1 and word in msgs[0]


def test_missing_fields_and_unknown_type():
    assert len(check({}, "humanoid")) == 3
    assert "Unknown model type" in check(GOOD, "dragon")[0]


def test_budget_override_and_file(tmp_path):
    assert check(GOOD, "animal", Budget(8000, 1024)) == []
    p = tmp_path / "report.json"
    import json
    p.write_text(json.dumps({**GOOD, "triangles": 9000}))
    assert "9,000" in check_file(p, "humanoid")[0]
