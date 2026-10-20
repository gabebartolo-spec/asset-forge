"""End-to-end run of the real app, over HTTP only (the calls the page makes; design 5.7).

    python tools/e2e/run_e2e.py OUT_DIR [--url http://127.0.0.1:7860] [--only humanoid,fox]
        [--generators hi3dgen,triposg] [--library library] [--refs models/bakeoff/refs]
        [--lock models/gpu.lock] [--no-gifs]

For each bake-off prompt (tools/bakeoff/prompts.toml) x each generator on the menu:
reference (draw from the words, or upload the bake-off reference when the app cannot draw yet)
-> generate -> clean -> skeleton -> animate -> export. A step that fails or is refused stops
that model; a refusal the app makes on purpose today (monsters at skeleton/animate) is
recorded as "refused", not "fail".

Per model it records each step's state, the app's plain error text, machine seconds, the gate
numbers (triangles, texture, bones, influences) and the Godot results, and copies the
reference, the five-view sheets (raw clay; clean clay and colour), the test-pose sheet and one
GIF per clip into OUT_DIR/<model>/. The sheets come through the file route (clean/after/...),
falling back to the library folder on disk for an older app. A monster's skeleton uses the
limb chains the app proposes, unedited (the director presses Build skeleton). GIFs come from
tools/animate/previews.py (under the shared GPU lock) because the API does not make them.
Writes OUT_DIR/index.json and OUT_DIR/index.md.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STEPS = ("reference", "generate", "clean", "skeleton", "animate", "export")
SHEET_VIEWS = ("front", "back", "left", "right", "three_quarter", "top")
CLIPS = ("idle", "walk", "run", "attack", "hit", "faint")
PASS, FAIL, REFUSED, SKIPPED = "pass", "fail", "refused", "skipped"
SEED = 1234  # one pinned seed per run so the two generators get the same chance


# ------------------------------------------------------------------ HTTP (stdlib only)

class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


class Api:
    """The few calls the page makes. `opener` is injectable for tests."""

    def __init__(self, base: str, opener: Callable[..., Any] | None = None,
                 poll_s: float = 3.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self.base = base.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.poll_s, self.sleep = poll_s, sleep

    def _send(self, req: urllib.request.Request) -> bytes:
        try:
            with self.opener(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(body).get("detail", body)
            except ValueError:
                detail = body
            raise ApiError(e.code, str(detail)) from None

    def get(self, path: str) -> Any:
        return json.loads(self._send(urllib.request.Request(self.base + path)))

    def get_bytes(self, path: str) -> bytes:
        return self._send(urllib.request.Request(self.base + path))

    def post(self, path: str, body: dict | None = None) -> Any:
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        return json.loads(self._send(req))

    def upload(self, path: str, image: Path, fields: dict[str, str]) -> Any:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                         f"{v}\r\n".encode())
        ctype = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                     f'filename="{image.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
                     + image.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            self.base + path, data=b"".join(parts), method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return json.loads(self._send(req))

    def wait(self, job: dict, timeout_s: float = 3600) -> dict:
        """Poll the job until it is done or failed (the page does the same, every second)."""
        t0 = time.time()
        while job.get("state") not in ("done", "failed"):
            if time.time() - t0 > timeout_s:
                return {**job, "state": "failed", "error": f"timed out after {timeout_s:.0f} s"}
            self.sleep(self.poll_s)
            job = self.get(f"/api/jobs/{job['id']}")
        return job


# ------------------------------------------------------------------ one model

def load_prompts(path: Path) -> list[dict]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [{"id": p["id"], "type": p["type"].lower(), "text": p["text"]} for p in data["prompt"]]


def step(state: str, seconds: float | None = None, error: str = "", **extra: Any) -> dict:
    return {"state": state, "seconds": seconds, "error": error, **extra}


def job_seconds(job: dict) -> float | None:
    res = job.get("result") or {}
    for key in ("total_s", "seconds"):
        if isinstance(res.get(key), int | float):
            return round(float(res[key]), 1)
    return job.get("elapsed_s")


def run_job(api: Api, path: str, body: dict | None = None) -> tuple[dict, dict | None]:
    """POST a step and wait for its job. Returns (step record, finished job or None)."""
    try:
        job = api.post(path, body)
    except ApiError as e:
        # 400 = the app refuses this on purpose today (monsters); 409/501 = a missing step.
        return step(REFUSED if e.status == 400 else FAIL, error=e.detail, http=e.status), None
    t0 = time.time()
    job = api.wait(job)
    wall = round(time.time() - t0, 1)
    if job["state"] != "done":
        return step(FAIL, job_seconds(job), job.get("error") or job.get("message") or "",
                    wall_s=wall), job
    return step(PASS, job_seconds(job), wall_s=wall), job


def run_model(api: Api, prompt: dict, generator: str, can_draw: bool, refs_dir: Path,
              seed: int = SEED) -> dict:
    rec: dict[str, Any] = {"model": f"{generator}_{prompt['id']}", "prompt_id": prompt["id"],
                           "type": prompt["type"], "generator": generator,
                           "prompt": prompt["text"], "asset_id": None, "steps": {},
                           "gates": {}, "godot": {}}
    steps = rec["steps"]

    def stop_rest(after: str) -> dict:
        for s in STEPS[STEPS.index(after) + 1:]:
            steps.setdefault(s, step(SKIPPED))
        return rec

    # 1. Reference picture
    t0 = time.time()
    try:
        if can_draw:
            asset = api.post("/api/assets/from-text", {"prompt": prompt["text"],
                                                       "type": prompt["type"]})
            rec["asset_id"] = asset["id"]
            st, _ = run_job(api, f"/api/assets/{asset['id']}/draw", {"seed": seed})
            steps["reference"] = {**st, "mode": "drawn from the words"}
        else:
            ref = refs_dir / f"{prompt['id']}.png"
            asset = api.upload("/api/assets", ref, {"type": prompt["type"]})
            rec["asset_id"] = asset["id"]
            steps["reference"] = step(PASS, round(time.time() - t0, 1),
                                      mode="bake-off reference uploaded (the app cannot draw yet)")
    except (ApiError, OSError) as e:
        steps["reference"] = step(FAIL, error=getattr(e, "detail", str(e)))
    if steps["reference"]["state"] != PASS:
        return stop_rest("reference")
    aid = rec["asset_id"]

    # 2. Generate
    st, job = run_job(api, f"/api/assets/{aid}/generate", {"generator": generator, "seed": seed})
    if job and job.get("result"):
        st["gpu_peak_gb"] = job["result"].get("gpu_peak_gb")
        if job["result"].get("anatomy"):
            st["anatomy"] = job["result"]["anatomy"]  # the Step 1 limb check (warns only)
    steps["generate"] = st
    if st["state"] != PASS:
        return stop_rest("generate")

    # 3. Clean: the job finishes, but a model that breaks a limit comes back passed False
    st, job = run_job(api, f"/api/assets/{aid}/clean")
    if job and job.get("result"):
        r = job["result"]
        rec["gates"].update({"triangles": r.get("triangles"),
                             "triangle_budget": r.get("triangle_budget"),
                             "raw_triangles": r.get("raw_triangles"),
                             "texture": r.get("texture"), "materials": r.get("materials"),
                             "silhouette": r.get("silhouette"),
                             "clean_problems": r.get("all_problems") or r.get("problems")})
        if st["state"] == PASS and not r.get("passed", True):
            words = r.get("all_problems") or r.get("problems") or ["Clean broke a limit."]
            st = {**st, "state": FAIL, "error": " ".join(words)}
    steps["clean"] = st
    if st["state"] != PASS:
        return stop_rest("clean")

    # 4. Skeleton (a monster sends the limb chains the app proposed, as a person would unedited)
    body = None
    if prompt["type"] == "monster":
        try:
            prop = api.get(f"/api/assets/{aid}/skeleton/limbs")
            body = {"spine": prop["spine"], "limbs": [{"kind": lb["kind"], "joints": lb["joints"]}
                                                      for lb in prop["limbs"]]}
            rec["gates"]["limbs_proposed"] = prop.get("counts")
        except (ApiError, KeyError, TypeError) as e:
            steps["skeleton"] = step(FAIL, error=getattr(e, "detail", f"no limb proposal: {e}"))
            return stop_rest("skeleton")
    st, job = run_job(api, f"/api/assets/{aid}/skeleton", body)
    if job and job.get("result"):
        r = job["result"]
        rec["gates"].update({"bones": r.get("bones"), "max_influences": r.get("max_influences"),
                             "template": r.get("template"),
                             "weights_method": r.get("weights_method")})
        if r.get("problems"):
            st["problems"] = r["problems"]
    steps["skeleton"] = st
    if st["state"] != PASS:
        return stop_rest("skeleton")

    # 5. Animate
    st, job = run_job(api, f"/api/assets/{aid}/animate")
    if job and job.get("result"):
        r = job["result"]
        st["checks"] = r.get("checks")
        st["clips"] = [c.get("name") for c in r.get("clips") or []]
    steps["animate"] = st
    if st["state"] != PASS:
        return stop_rest("animate")

    # 6. Export: the budget gate and the headless Godot checks
    st, job = run_job(api, f"/api/assets/{aid}/export")
    if job and job.get("result"):
        r = job["result"]
        m = r.get("measured") or {}
        rec["gates"].update({"export_measured": m})
        rec["godot"] = {"rig": r.get("godot_rig"), "import": r.get("godot_import"),
                        "folder": r.get("folder")}
    elif st["state"] == FAIL:
        rec["godot"] = {"refused": st["error"]}
    steps["export"] = st
    return rec


# ------------------------------------------------------------------ summary (unit tested)

def model_total_s(rec: dict) -> float:
    return round(sum(s.get("seconds") or 0.0 for s in rec["steps"].values()), 1)


def furthest(rec: dict) -> str:
    """The last step that passed ("none" if even the reference failed)."""
    last = "none"
    for s in STEPS:
        if rec["steps"].get(s, {}).get("state") == PASS:
            last = s
        else:
            break
    return last


def summarise(records: list[dict]) -> dict:
    per_step = {s: {PASS: 0, FAIL: 0, REFUSED: 0, SKIPPED: 0} for s in STEPS}
    for rec in records:
        for s in STEPS:
            state = rec["steps"].get(s, {}).get("state", SKIPPED)
            per_step[s][state] += 1
    end_to_end = sum(1 for r in records if furthest(r) == "export")
    failures = [{"model": r["model"], "step": s, "error": r["steps"][s].get("error", "")}
                for r in records for s in STEPS if r["steps"].get(s, {}).get("state") == FAIL]
    refusals = [{"model": r["model"], "step": s, "error": r["steps"][s].get("error", "")}
                for r in records for s in STEPS if r["steps"].get(s, {}).get("state") == REFUSED]
    return {"models": len(records), "end_to_end": end_to_end, "per_step": per_step,
            "failures": failures, "refusals": refusals,
            "total_s": {r["model"]: model_total_s(r) for r in records}}


def render_md(index: dict) -> str:
    mark = {PASS: "pass", FAIL: "FAIL", REFUSED: "refused", SKIPPED: "-"}
    lines = [f"# Asset Forge end-to-end run: {index['run']}", "",
             f"App {index['url']} at commit {index.get('commit', '?')}; "
             f"{index['summary']['end_to_end']} of {index['summary']['models']} models reached "
             "export.", "", "| Model | " + " | ".join(STEPS) + " | Machine s | Tris | Bones |",
             "|---" * (len(STEPS) + 4) + "|"]
    for r in index["models"]:
        cells = [mark[r["steps"].get(s, {}).get("state", SKIPPED)] for s in STEPS]
        g = r.get("gates", {})
        tris = (g.get("export_measured") or {}).get("triangles", g.get("triangles"))
        lines.append(f"| {r['model']} | " + " | ".join(cells)
                     + f" | {model_total_s(r):.0f} | {tris if tris is not None else '-'} | "
                     f"{g.get('bones', '-')} |")
    s = index["summary"]
    if s["failures"]:
        lines += ["", "## Failures"] + [f"- {f['model']} at {f['step']}: {f['error']}"
                                        for f in s["failures"]]
    if s["refusals"]:
        lines += ["", "## Refused on purpose today"] + [
            f"- {f['model']} at {f['step']}: {f['error']}" for f in s["refusals"]]
    lines += ["", "Files per model: `<model>/` (reference.png, sheet_raw_clay.png, "
              "sheet_clean_clay.png, sheet_clean_colour.png, pose_clay.png, pose_colour.png, "
              "clips/*.gif). Raw models carry no colour (the generators are geometry only), so "
              "there is no textured raw sheet.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ files

def grid(paths: list[Path], dest: Path, cols: int = 3, tile: int = 384) -> bool:
    from PIL import Image, ImageDraw

    paths = [p for p in paths if p.is_file()]
    if not paths:
        return False
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows * (tile + 24)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((tile, tile))
        x, y = (i % cols) * tile, (i // cols) * (tile + 24)
        sheet.paste(im, (x + (tile - im.width) // 2, y + 24))
        draw.text((x + 6, y + 6), p.stem, fill="black")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return True


def collect_files(api: Api, rec: dict, library: Path, out: Path) -> list[str]:
    aid = rec["asset_id"]
    if not aid:
        return []
    d = out / rec["model"]
    d.mkdir(parents=True, exist_ok=True)
    made = []
    try:
        (d / "reference.png").write_bytes(api.get_bytes(f"/api/assets/{aid}/files/generate/"
                                                        "input.png"))
        made.append("reference.png")
    except ApiError:
        pass
    tmp = d / "_views"

    def fetch(step_name: str, name: str) -> Path:
        """One view through the file route; the library folder on disk if the app refuses."""
        dest = tmp / step_name / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(api.get_bytes(f"/api/assets/{aid}/files/{step_name}/{name}"))
            rec.setdefault("views_via", set()).add("api")
        except ApiError:
            src = library / aid / step_name / name
            if not src.is_file():
                return src
            shutil.copy2(src, dest)
            rec.setdefault("views_via", set()).add("disk")
        return dest

    for name, folder, shade in (("sheet_raw_clay", "before", "clay"),
                                ("sheet_clean_clay", "after", "clay"),
                                ("sheet_clean_colour", "after", "colour")):
        if grid([fetch("clean", f"{folder}/{v}_{shade}.png") for v in SHEET_VIEWS],
                d / f"{name}.png"):
            made.append(f"{name}.png")
    for shade in ("clay", "colour"):
        if grid([fetch("skeleton", f"pose_{v}_{shade}.png") for v in SHEET_VIEWS],
                d / f"pose_{shade}.png"):
            made.append(f"pose_{shade}.png")
    rec["views_via"] = sorted(rec.get("views_via", ()))
    shutil.rmtree(tmp, ignore_errors=True)
    return made


def make_gifs(records: list[dict], library: Path, out: Path, lock: Path) -> str:
    """Stage every animated model's rigged.blend as <gen>/<body>/rigged.blend and let
    tools/animate/previews.py render one GIF per clip under the GPU lock."""
    stage = out / "_rigs"
    todo = [r for r in records if r["steps"].get("animate", {}).get("state") == PASS]
    for r in todo:
        src = library / r["asset_id"] / "skeleton" / "rigged.blend"
        dst = stage / r["generator"] / r["prompt_id"] / "rigged.blend"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if not todo:
        return "no animated models"
    gifs = out / "_gifs"
    p = subprocess.run([sys.executable, str(REPO / "tools" / "animate" / "previews.py"),
                        str(stage), str(gifs), "--lock", str(lock)],
                       capture_output=True, text=True)
    for r in todo:
        d = out / r["model"] / "clips"
        d.mkdir(parents=True, exist_ok=True)
        for c in CLIPS:
            g = gifs / f"{r['generator']}_{r['prompt_id']}_{c}.gif"
            if g.is_file():
                shutil.move(str(g), d / f"{c}.gif")
                r.setdefault("files", []).append(f"clips/{c}.gif")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(gifs, ignore_errors=True)
    return (p.stdout + p.stderr)[-4000:]


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--only", default="")
    ap.add_argument("--generators", default="")
    ap.add_argument("--library", type=Path, default=REPO / "library")
    ap.add_argument("--refs", type=Path, default=REPO / "models" / "bakeoff" / "refs")
    ap.add_argument("--lock", type=Path, default=REPO / "models" / "gpu.lock")
    ap.add_argument("--no-gifs", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    api = Api(a.url)
    menu = api.get("/api/menu")
    gens = [g["id"] for g in menu["generators"]]
    if a.generators:
        gens = [g for g in gens if g in a.generators.split(",")]
    can_draw = bool((menu.get("text_draw") or {}).get("available"))
    prompts = load_prompts(REPO / "tools" / "bakeoff" / "prompts.toml")
    if a.only:
        prompts = [p for p in prompts if p["id"] in a.only.split(",")]
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    index = {"run": a.out.name, "url": a.url, "commit": commit, "started": time.ctime(),
             "can_draw": can_draw, "generators": gens, "models": []}

    def save() -> None:
        index["summary"] = summarise(index["models"])
        (a.out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
        (a.out / "index.md").write_text(render_md(index), encoding="utf-8")

    for p in prompts:
        for g in gens:
            print(f"== {g} {p['id']}", flush=True)
            rec = run_model(api, p, g, can_draw, a.refs)
            rec["files"] = collect_files(api, rec, a.library, a.out)
            index["models"].append(rec)
            print("   " + " ".join(f"{s}={rec['steps'][s]['state']}" for s in STEPS)
                  + f" ({model_total_s(rec):.0f} s)", flush=True)
            save()
    if not a.no_gifs:
        index["gif_log"] = make_gifs(index["models"], a.library, a.out, a.lock)
    index["finished"] = time.ctime()
    save()
    print(render_md(index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
