import time

import pytest
from conftest import FakeGenerator, make_png
from fastapi.testclient import TestClient
from PIL import Image

from asset_forge.api import create_app
from asset_forge.config import Settings, load_settings
from asset_forge.generators import Registry


@pytest.fixture
def client(settings, fake_registry):
    app = create_app(settings, fake_registry)
    with TestClient(app) as c:
        yield c
    app.state.queue.shutdown()


def upload(client, type_="humanoid", data=None):
    return client.post("/api/assets",
                       files={"image": ("ref.png", data or make_png(), "image/png")},
                       data={"type": type_})


def finish(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_menu_lists_generators_in_config_order_with_first_preselected(client):
    m = client.get("/api/menu").json()
    assert [t["label"] for t in m["types"]] == ["Humanoid", "Monster", "Animal"]
    assert [g["id"] for g in m["generators"]] == ["hi3dgen", "triposg"]
    assert [g["selected"] for g in m["generators"]] == [True, False]
    for g in m["generators"]:
        assert g["typical_time"] and "VRAM" in g["vram"]
        assert g["label"] and "Heavier" not in g["blurb"]


def test_real_menu_order_comes_from_settings(tmp_path):
    s = Settings(models_dir=tmp_path, library_dir=tmp_path / "lib")
    assert [g.id for g in Registry.from_settings(s).generators] == ["hi3dgen", "triposg"]
    s.generator_order = ["triposg", "hi3dgen"]
    reg = Registry.from_settings(s)
    assert [g["id"] for g in reg.menu()] == ["triposg", "hi3dgen"]
    assert reg.menu()[0]["selected"] is True


def test_config_file_sets_order_and_host_is_always_localhost(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[app]\nhost = "0.0.0.0"\nport = 9000\n[generators]\norder = ["triposg"]\n')
    s = load_settings(cfg)
    assert s.generator_order == ["triposg"] and s.port == 9000 and s.host == "127.0.0.1"


def test_generate_writes_the_step_folder_with_settings_and_seed(client, settings):
    a = upload(client).json()
    r = client.post(f"/api/assets/{a['id']}/generate", json={"generator": "triposg", "seed": 42})
    assert r.status_code == 200
    j = finish(client, r.json()["id"])
    assert j["state"] == "done" and j["result"]["seed"] == 42
    step = settings.library_dir / a["id"] / "generate"
    assert (step / "raw.glb").exists() and (step / "input.png").exists()
    asset = client.get(f"/api/assets/{a['id']}").json()
    gen = asset["steps"]["generate"]
    assert gen["settings"]["generator"] == "triposg" and gen["settings"]["seed"] == 42
    assert gen["result"]["gpu_peak_gb"] == 2.0 and asset["reached"] == "generate"
    f = client.get(f"/api/assets/{a['id']}/files/generate/raw.glb")
    assert f.status_code == 200 and f.content == b"glTF-fake"


def test_redo_keeps_the_picture_and_picks_a_new_seed(client, fake_registry):
    a = upload(client).json()
    seeds = []
    for _ in range(3):
        j = client.post(f"/api/assets/{a['id']}/generate", json={"generator": "hi3dgen"}).json()
        seeds.append(finish(client, j["id"])["result"]["seed"])
    assert len(set(seeds)) == 3
    assert fake_registry.get("hi3dgen").seeds == seeds


def test_failure_reports_plain_words_and_is_saved(client):
    client.app.state.registry.generators[0].fail = True
    a = upload(client).json()
    j = client.post(f"/api/assets/{a['id']}/generate", json={"generator": "hi3dgen"}).json()
    done = finish(client, j["id"])
    assert done["state"] == "failed" and "Press Redo" in done["error"]
    saved = client.get(f"/api/assets/{a['id']}").json()["steps"]["generate"]["status"]
    assert saved["state"] == "failed"


def test_two_assets_queue_and_never_overlap(settings):
    log = []
    reg = Registry([FakeGenerator("hi3dgen", "Hi3DGen", sleep=0.1, log=log)])
    app = create_app(settings, reg)
    with TestClient(app) as c:
        ids = []
        for _ in range(2):
            a = upload(c).json()
            ids.append(c.post(f"/api/assets/{a['id']}/generate",
                              json={"generator": "hi3dgen"}).json()["id"])
        for i in ids:
            finish(c, i)
    app.state.queue.shutdown()
    assert [e[0] for e in log] == ["start", "end", "start", "end"]


def test_bad_requests_get_plain_errors(client):
    r = upload(client, data=b"not a picture")
    assert r.status_code == 400 and "not a picture" in r.json()["detail"]
    assert upload(client, type_="dragon").status_code == 400
    a = upload(client).json()
    r = client.post(f"/api/assets/{a['id']}/generate", json={"generator": "nope"})
    assert r.status_code == 400 and "Pick one" in r.json()["detail"]
    assert client.get("/api/assets/a-20260101-000000-abcd").status_code == 404
    assert client.get("/api/jobs/zzz").status_code == 404
    assert client.get(f"/api/assets/{a['id']}/files/generate/..%2Fasset.json").status_code == 404


def test_hooks_for_later_steps_say_coming_next(client):
    a = upload(client).json()
    r = client.post(f"/api/assets/{a['id']}/clean")
    assert r.status_code == 501 and "coming next" in r.json()["detail"]
    r = client.post("/api/assets/from-text")
    assert r.status_code == 501 and "coming next" in r.json()["detail"]


def test_an_already_cut_out_picture_is_kept(client, settings):
    a = upload(client, data=make_png(plain_background=False)).json()
    im = Image.open(settings.library_dir / a["id"] / "generate" / "input.png")
    assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0 and im.getpixel((100, 100))[3] == 255


def test_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Asset Forge" in r.text
    assert client.get("/app.js").headers["content-type"].startswith("text/javascript")


def test_job_status_tells_waiting_for_the_gpu_from_running(settings):
    """The page shows 'Waiting for the graphics card' vs 'Making your model' + a timer."""
    lock = settings.lock_dir
    lock.mkdir(parents=True)
    (lock / "owner.txt").write_text("sprites:batch pid=1\n")
    reg = Registry([FakeGenerator("hi3dgen", "Hi3DGen", sleep=0.4)])
    app = create_app(settings, reg)
    with TestClient(app) as c:
        a = upload(c).json()
        jid = c.post(f"/api/assets/{a['id']}/generate", json={"generator": "hi3dgen"}).json()["id"]
        end = time.time() + 5
        while time.time() < end and c.get(f"/api/jobs/{jid}").json()["state"] != "waiting":
            time.sleep(0.02)
        waiting = c.get(f"/api/jobs/{jid}").json()
        assert waiting["state"] == "waiting" and waiting["started"] is None
        assert waiting["elapsed_s"] == 0.0 and "sprites:batch" in waiting["message"]
        (lock / "owner.txt").unlink()
        lock.rmdir()
        while time.time() < end and c.get(f"/api/jobs/{jid}").json()["state"] != "running":
            time.sleep(0.02)
        running = c.get(f"/api/jobs/{jid}").json()
        assert running["state"] == "running" and running["started"] is not None
        time.sleep(0.15)
        assert c.get(f"/api/jobs/{jid}").json()["elapsed_s"] > 0
        assert finish(c, jid)["state"] == "done"
    app.state.queue.shutdown()
