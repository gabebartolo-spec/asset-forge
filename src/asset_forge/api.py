"""The backend: a FastAPI app on 127.0.0.1. Every step is an API call first and a button second
(design 5.7), so the page and a future Claude MCP server use the same calls.

    GET  /api/menu                        types and the generator menu (order from config)
    POST /api/assets                      multipart: image, type -> new asset (picture cut out)
    POST /api/assets/{id}/generate        {generator, seed?} -> job (queued on the one GPU queue)
    GET  /api/jobs/{job_id}               state, plain-words message, elapsed time
    GET  /api/assets, /api/assets/{id}    the library
    GET  /api/assets/{id}/files/{step}/{name}   an output (raw.glb, input.png, ...)
    POST /api/assets/{id}/clean           Step 2 hook (not wired yet: 501)
    POST /api/assets/{id}/skeleton        Step 3: fit, bind, test pose (queued; needs clean.glb).
                                          A monster sends its confirmed {spine, limbs}
    GET  /api/assets/{id}/skeleton/limbs  a monster's proposed limb chains and counts
                                          (?fresh=1: the proposal, not the confirmed limbs)
    GET  /api/library[?trash=1]           cards: thumbnail flag, type, date, last step, timings
    POST /api/assets/{id}/duplicate, /trash, /restore   copy, move to library/_trash, put back
    POST /api/batch, GET /api/batch/{id}  several prompts through draw + 3D on the one queue
    POST /api/expand                      {idea, type, variation?} -> job; result {prompt}
                                          ("Expand my idea", on the one GPU queue)
    POST /api/assets/from-text            {prompt, type} -> new asset with no picture yet
    POST /api/assets/{id}/draw            {prompt?, seed?} -> job: draws input.png from the words
                                          (re-roll = call again); 501 until the SDXL drawer lands
"""

from __future__ import annotations

import io
import json
import mimetypes
import secrets
import struct
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .anatomy import check_mesh
from .config import Settings, load_settings
from .draw import DrawError, ReferenceDrawer, default_drawer
from .generators import Registry
from .jobqueue import GpuQueue, Job
from .library import register_library
from .matte import prepare_reference
from .skeleton import rig
from .skeleton.monster import ChainError, monster_bones
from .store import ASSET_TYPES, NotFound, Store

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("model/gltf-binary", ".glb")

TYPE_LABELS = {"humanoid": "Humanoid", "monster": "Monster", "animal": "Animal"}
MAX_UPLOAD = 25 * 1024 * 1024
MAX_WORDS = 600


class GenerateRequest(BaseModel):
    generator: str
    seed: int | None = None


class ExpandRequest(BaseModel):
    idea: str
    type: str
    variation: int = 0  # 0 = the first version; each re-roll sends a new number


class TextAssetRequest(BaseModel):
    prompt: str
    type: str


class DrawRequest(BaseModel):
    prompt: str | None = None
    seed: int | None = None


Expander = Callable[[str, str, int | None], str]


def real_expander(idea: str, asset_type: str, seed: int | None) -> str:
    """The Qwen prompt writer (src/asset_forge/prompts). It runs in its own env and stays
    loaded after the first call (about 4.2 GB of VRAM) until `release_idea_writer` frees it."""
    from . import prompts
    from .generators import GeneratorError

    try:
        return prompts.expand(idea, asset_type, seed=seed)
    except prompts.PromptGenError as e:
        raise GeneratorError("The idea writer could not run. Type the full description "
                             "yourself, or try Expand my idea again.") from e


def release_idea_writer() -> None:
    from .prompts import llm

    llm.stop()


def create_app(settings: Settings | None = None, registry: Registry | None = None,
               queue: GpuQueue | None = None, expander: Expander | None = None,
               drawer: ReferenceDrawer | None = None,
               release_writer: Callable[[], None] | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = Store(settings.library_dir)
    store.fail_unfinished()
    registry = registry or Registry.from_settings(settings)

    def persist(job: Job) -> None:
        try:
            store.write_status(job.asset_id, job.step, job.public())
            if job.state == "done" and job.started and job.finished:
                res = job.result or {}
                if res.get("timings"):  # a batch job reports its draw and 3D seconds itself
                    for key, secs in res["timings"].items():
                        store.record_timing(job.asset_id, key, secs)
                else:  # a draw runs as "generate" too, but only it reports draw_s
                    store.record_timing(job.asset_id, "draw" if "draw_s" in res else job.step,
                                        job.finished - job.started)
        except NotFound:
            pass

    expander = expander or real_expander
    drawer = drawer or default_drawer(settings)
    release_writer = release_writer or release_idea_writer

    gpu_queue = queue or GpuQueue(settings.lock_dir, persist=persist)
    if queue is not None:
        gpu_queue.persist = persist

    app = FastAPI(title="Asset Forge", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.queue = gpu_queue
    app.state.registry = registry
    app.state.settings = settings

    def missing(what: str) -> HTTPException:
        return HTTPException(404, f"I could not find that {what}. Go back and start again.")

    @app.get("/api/menu")
    def menu() -> dict:
        return {
            "types": [{"id": t, "label": TYPE_LABELS[t]} for t in ASSET_TYPES],
            "generators": registry.menu(),
            "text_draw": {"available": drawer.available, "note": drawer.note},
        }

    @app.post("/api/assets")
    async def create_asset(image: UploadFile = File(...),  # noqa: B008
                           type: str = Form(...)) -> dict:  # noqa: A002, B008
        data = await image.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, "That picture is too big. Use one under 25 MB.")
        try:
            cut = prepare_reference(data)
            buf = io.BytesIO()
            cut.save(buf, "PNG")
            return store.create_asset(type, buf.getvalue())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    def need_drawer() -> None:
        if not drawer.available:
            raise HTTPException(501, drawer.note)

    def clean_words(text: str, what: str) -> str:
        text = " ".join(text.split())
        if not text:
            raise HTTPException(400, f"Type {what} first.")
        if len(text) > MAX_WORDS:
            raise HTTPException(400, "That is too long. Please keep it under 600 letters.")
        return text

    def draw_now(asset_id: str, asset_type: str, prompt: str, seed: int,
                 progress: Callable[[str], None]) -> dict:
        """Draw input.png from the words (inside a queue job; the batch uses it too)."""
        release_writer()  # the idea writer must not hold VRAM while the picture is drawn
        t0 = time.time()
        png = drawer.draw(prompt, asset_type, seed, progress)
        buf = io.BytesIO()
        try:
            prepare_reference(png).save(buf, "PNG")
        except ValueError as e:
            raise DrawError("The drawing came out empty. Press Draw another.") from e
        (store.step_dir(asset_id, "generate") / "input.png").write_bytes(buf.getvalue())
        return {"seed": seed, "draw_s": round(time.time() - t0, 1)}

    def generate_now(asset_id: str, generator, seed: int,
                     progress: Callable[[str], None]) -> dict:
        """Run the 3D maker on input.png (inside a queue job; the batch uses it too)."""
        release_writer()  # free the idea writer's VRAM before a 3D run
        sd = store.step_dir(asset_id, "generate")
        t0 = time.time()
        res = generator.run(sd / "input.png", sd, seed, progress)
        result = {
            "generator": generator.id, "seed": seed, "mesh": res.mesh.name,
            "total_s": round(time.time() - t0, 1), "gen_s": res.gen_s,
            "gpu_peak_gb": res.gpu_peak_gb, "details": res.details,
        }
        progress("Counting legs and arms...")
        result["anatomy"] = limb_check(asset_id, res.mesh)
        store.write_result(asset_id, "generate", result)
        store.mark_reached(asset_id, "generate")
        return result

    @app.post("/api/expand")
    def expand_idea(req: ExpandRequest) -> dict:
        idea = clean_words(req.idea, "a few words")
        if req.type not in ASSET_TYPES:
            raise HTTPException(400, "Choose Humanoid, Monster or Animal first.")
        seed = req.variation if req.variation > 0 else None

        def run(job: Job) -> dict:
            job.set_message("Writing your description...")
            return {"prompt": expander(idea, req.type, seed)}

        return gpu_queue.submit("expand", "expand", run).public()

    @app.post("/api/assets/from-text")
    def from_text(req: TextAssetRequest) -> dict:
        need_drawer()
        prompt = clean_words(req.prompt, "a description")
        try:
            return store.create_text_asset(req.type, prompt)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/assets/{asset_id}/draw")
    def draw_reference(asset_id: str, req: DrawRequest) -> dict:
        need_drawer()
        try:
            asset = store.get_asset(asset_id)
        except NotFound:
            raise missing("model") from None
        prompt = clean_words(req.prompt or asset.get("prompt") or "", "a description")
        store.set_prompt(asset_id, prompt)
        seed = req.seed if req.seed is not None else secrets.randbelow(2**31)

        def run(job: Job) -> dict:
            return draw_now(asset_id, asset["type"], prompt, seed, job.set_message)

        return gpu_queue.submit(asset_id, "generate", run).public()

    @app.get("/api/assets")
    def list_assets() -> list[dict]:
        return store.list_assets()

    @app.get("/api/assets/{asset_id}")
    def get_asset(asset_id: str) -> dict:
        try:
            return store.get_asset(asset_id)
        except NotFound:
            raise missing("model") from None

    @app.post("/api/assets/{asset_id}/generate")
    def generate(asset_id: str, req: GenerateRequest) -> dict:
        try:
            asset = store.get_asset(asset_id)
            generator = registry.get(req.generator)
        except NotFound:
            raise missing("model") from None
        except KeyError:
            raise HTTPException(400, "Pick one of the generators in the list.") from None
        if not (store.step_dir(asset_id, "generate") / "input.png").is_file():
            raise HTTPException(400, "Draw the picture first, then make the 3D model.")
        seed = req.seed if req.seed is not None else secrets.randbelow(2**31)
        store.write_settings(asset_id, "generate", {
            "generator": generator.id, "seed": seed, "type": asset["type"],
            "requested": time.time(),
        })

        def run(job: Job) -> dict:
            return generate_now(asset_id, generator, seed, job.set_message)

        job = gpu_queue.submit(asset_id, "generate", run)
        return job.public()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = gpu_queue.jobs.get(job_id)
        if job is None:
            raise missing("job")
        out = job.public()
        out["ahead"] = gpu_queue.ahead_of(job)
        return out

    @app.get("/api/assets/{asset_id}/files/{step}/{name}")
    def get_file(asset_id: str, step: str, name: str) -> FileResponse:
        try:
            p = store.file_path(asset_id, step, name)
        except NotFound:
            raise missing("file") from None
        return FileResponse(p, headers={"Cache-Control": "no-cache"})

    @app.post("/api/assets/{asset_id}/clean")
    def clean(asset_id: str) -> JSONResponse:
        # Step 2 hook: will run steps.clean_command(...) on the queue, then show clean.glb.
        return JSONResponse(
            {"detail": "Cleaning up the model is coming next."}, status_code=501)

    def limb_check(asset_id: str, mesh) -> dict | None:
        """Step 1 limb gate: count legs and arms against the words (None = nothing to check)."""
        asset = store.get_asset(asset_id)
        return check_mesh(mesh, asset.get("prompt"), asset["type"])

    @app.get("/api/assets/{asset_id}/skeleton/limbs")
    def monster_limbs(asset_id: str, fresh: bool = False) -> dict:
        """A monster's proposed limb chains, worked out once from its shape and kept; the user's
        edits are sent back with Build skeleton (no automatic re-proposal). fresh: the app's
        own proposal again, leaving out the limbs the user confirmed (Start the limbs again)."""
        try:
            store.get_asset(asset_id)
            clean_glb = store.step_dir(asset_id, "clean") / "clean.glb"
            out = store.step_dir(asset_id, "skeleton")
        except NotFound:
            raise missing("model") from None
        if not clean_glb.is_file():
            raise HTTPException(409, "Clean up the model first, then build its skeleton.")
        for name in ("proposal.json",) if fresh else ("chain.json", "proposal.json"):
            if (out / name).is_file():
                data = json.loads((out / name).read_text(encoding="utf-8"))
                return {**data, "confirmed": name == "chain.json"}
        from .skeleton.glb import read_mesh
        from .skeleton.limbs import propose

        try:
            data = propose(*read_mesh(clean_glb)).public()
        except (OSError, ValueError, KeyError, IndexError, struct.error):
            raise HTTPException(500, "I could not find the limbs on this model. "
                                     "Go back to step 1 and press Redo.") from None
        out.mkdir(parents=True, exist_ok=True)
        (out / "proposal.json").write_text(json.dumps(data), encoding="utf-8")
        return {**data, "confirmed": False}

    def confirmed_chain(asset_id: str, body: dict | None) -> Path:
        """Check the monster's edited limb chains and keep them as skeleton/chain.json."""
        if not body or "limbs" not in body:
            raise HTTPException(400, "Check the limb markers, then press Build skeleton.")
        try:
            monster_bones(body)
        except ChainError as e:
            raise HTTPException(400, str(e)) from None
        out = store.step_dir(asset_id, "skeleton")
        out.mkdir(parents=True, exist_ok=True)
        path = out / "chain.json"
        keep = {"spine": body["spine"], "limbs": [
            {"kind": lb["kind"], "joints": lb["joints"]} for lb in body["limbs"]]}
        path.write_text(json.dumps(keep), encoding="utf-8")
        return path

    def markers_outside(clean_glb: Path, chain: Path) -> list[list[int]]:
        """[limb, joint] of every confirmed marker outside the body (limb -1: the body line)."""
        from .skeleton.glb import read_mesh
        from .skeleton.limbs import outside_joints

        found = outside_joints(*read_mesh(clean_glb), json.loads(chain.read_text("utf-8")))
        return [list(x) for x in found]

    @app.post("/api/assets/{asset_id}/skeleton")
    def skeleton(asset_id: str, body: dict | None = Body(None)) -> dict:  # noqa: B008
        # TODO(PR #9): the Clean step will write library/<id>/clean/clean.glb through this
        # app; until it is merged the file is placed there by hand and the Step 2 -> Step 3
        # hand-over button does not exist yet.
        try:
            asset = store.get_asset(asset_id)
            clean_glb = store.step_dir(asset_id, "clean") / "clean.glb"
            out = store.step_dir(asset_id, "skeleton")
        except NotFound:
            raise missing("model") from None
        if not clean_glb.is_file():
            raise HTTPException(409, "Clean up the model first, then build its skeleton.")
        chain = confirmed_chain(asset_id, body) if asset["type"] == "monster" else None

        def run(job: Job) -> dict:
            job.set_message("Fitting the skeleton to your model...")
            t0 = time.time()
            res = rig(clean_glb, out, asset["type"], settings.blender_exe, repo=settings.repo,
                      **({"chain": chain} if chain else {}))
            result = {**res.public(), "total_s": round(time.time() - t0, 1)}
            if chain:
                result["outside"] = markers_outside(clean_glb, chain)
            store.write_result(asset_id, "skeleton", result)
            store.mark_reached(asset_id, "skeleton")
            return result

        return gpu_queue.submit(asset_id, "skeleton", run).public()

    register_library(app, store, gpu_queue, registry, drawer, draw_now, generate_now)

    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


def default_app() -> FastAPI:
    return create_app()


def main() -> None:
    import uvicorn

    s = load_settings()
    print(f"Asset Forge is running at http://{s.host}:{s.port}  (close this window to stop it)")
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="warning")



