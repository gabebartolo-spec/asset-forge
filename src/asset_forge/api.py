"""The backend: a FastAPI app on 127.0.0.1. Every step is an API call first and a button second
(design 5.7), so the page and a future Claude MCP server use the same calls.

    GET  /api/menu                        types and the generator menu (order from config)
    POST /api/assets                      multipart: image, type -> new asset (picture cut out)
    POST /api/assets/{id}/generate        {generator, seed?} -> job (queued on the one GPU queue)
    GET  /api/jobs/{job_id}               state, plain-words message, elapsed time
    GET  /api/assets, /api/assets/{id}    the library
    GET  /api/assets/{id}/files/{step}/{name}   an output (raw.glb, input.png, ...)
    POST /api/assets/{id}/clean           Step 2 hook (not wired yet: 501)
    POST /api/assets/from-text            text-only input (not built yet: 501)
"""

from __future__ import annotations

import io
import mimetypes
import secrets
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings, load_settings
from .generators import Registry
from .jobqueue import GpuQueue, Job
from .matte import prepare_reference
from .store import ASSET_TYPES, NotFound, Store

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("model/gltf-binary", ".glb")

TYPE_LABELS = {"humanoid": "Humanoid", "monster": "Monster", "animal": "Animal"}
MAX_UPLOAD = 25 * 1024 * 1024


class GenerateRequest(BaseModel):
    generator: str
    seed: int | None = None


def create_app(settings: Settings | None = None, registry: Registry | None = None,
               queue: GpuQueue | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = Store(settings.library_dir)
    store.fail_unfinished()
    registry = registry or Registry.from_settings(settings)

    def persist(job: Job) -> None:
        try:
            store.write_status(job.asset_id, job.step, job.public())
        except NotFound:
            pass

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

    @app.post("/api/assets/from-text")
    def from_text() -> JSONResponse:
        return JSONResponse(
            {"detail": "Describing a character in words is coming next. For now, choose a "
                       "picture."}, status_code=501)

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
        seed = req.seed if req.seed is not None else secrets.randbelow(2**31)
        store.write_settings(asset_id, "generate", {
            "generator": generator.id, "seed": seed, "type": asset["type"],
            "requested": time.time(),
        })

        def run(job: Job) -> dict:
            sd = store.step_dir(asset_id, "generate")
            t0 = time.time()
            res = generator.run(sd / "input.png", sd, seed, job.set_message)
            result = {
                "generator": generator.id, "seed": seed, "mesh": res.mesh.name,
                "total_s": round(time.time() - t0, 1), "gen_s": res.gen_s,
                "gpu_peak_gb": res.gpu_peak_gb, "details": res.details,
            }
            store.write_result(asset_id, "generate", result)
            store.mark_reached(asset_id, "generate")
            return result

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



