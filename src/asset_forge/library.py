"""Library tab and batch queue (design 5.4, 5.5). Routes only; the files live in store.py and
the work runs on the one GPU queue.

Batch: each prompt becomes a text-only asset and ONE queue job (draw the picture, then make the
3D model). Jobs run one after another in the order queued, so a batch and a single Make press
share the one GPU in turn. Clean up is not wired yet (501 in api.py); when it is, add it to
`run` here so a batch stops at Skeleton as the design says.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .draw import ReferenceDrawer
from .generators import Registry
from .jobqueue import GpuQueue, Job
from .store import ASSET_TYPES, NotFound, Store

MAX_BATCH = 20
MAX_WORDS = 600


class BatchItem(BaseModel):
    prompt: str
    type: str


class BatchRequest(BaseModel):
    items: list[BatchItem]
    generator: str | None = None


def register_library(app: FastAPI, store: Store, queue: GpuQueue, registry: Registry,
                     drawer: ReferenceDrawer, draw_now: Callable, generate_now: Callable) -> None:
    batches: dict[str, list[dict]] = {}

    def missing(what: str) -> HTTPException:
        return HTTPException(404, f"I could not find that {what}. Go back and start again.")

    @app.get("/api/library")
    def library(trash: int = 0) -> list[dict]:
        return store.cards(trashed=bool(trash))

    @app.post("/api/assets/{asset_id}/duplicate")
    def duplicate(asset_id: str) -> dict:
        try:
            if _busy(queue, asset_id):
                raise HTTPException(409, "It is still being made. Wait for it to finish.")
            return store.duplicate(asset_id)
        except NotFound:
            raise missing("model") from None

    @app.post("/api/assets/{asset_id}/trash")
    def trash(asset_id: str) -> dict:
        try:
            if _busy(queue, asset_id):
                raise HTTPException(409, "It is still being made. Wait for it to finish.")
            store.trash(asset_id)
        except NotFound:
            raise missing("model") from None
        return {"trashed": asset_id}

    @app.post("/api/assets/{asset_id}/restore")
    def restore(asset_id: str) -> dict:
        try:
            store.restore(asset_id)
        except NotFound:
            raise missing("model") from None
        return {"restored": asset_id}

    @app.post("/api/batch")
    def start_batch(req: BatchRequest) -> dict:
        if not drawer.available:
            raise HTTPException(501, drawer.note)
        if not req.items:
            raise HTTPException(400, "Add at least one description first.")
        if len(req.items) > MAX_BATCH:
            raise HTTPException(400, f"Queue up to {MAX_BATCH} at a time.")
        try:
            generator = registry.get(req.generator) if req.generator else registry.generators[0]
        except KeyError:
            raise HTTPException(400, "Pick one of the generators in the list.") from None
        clean = []
        for n, it in enumerate(req.items, 1):
            words = " ".join(it.prompt.split())
            if not words:
                raise HTTPException(400, f"Line {n} is empty. Type a description or remove it.")
            if len(words) > MAX_WORDS:
                raise HTTPException(400, f"Line {n} is too long. Keep it under 600 letters.")
            if it.type not in ASSET_TYPES:
                raise HTTPException(400, f"Line {n}: choose Humanoid, Monster or Animal.")
            clean.append((words, it.type))
        total = len(clean)
        items = []
        for n, (words, kind) in enumerate(clean, 1):
            asset = store.create_text_asset(kind, words)
            seed = secrets.randbelow(2**31)
            store.write_settings(asset["id"], "generate", {
                "generator": generator.id, "seed": seed, "type": kind, "requested": time.time()})

            def run(job: Job, aid=asset["id"], kind=kind, words=words, seed=seed, n=n) -> dict:
                tag = f"Model {n} of {total}: "
                drew = draw_now(aid, kind, words, seed, lambda m: job.set_message(tag + m))
                res = generate_now(aid, generator, seed, lambda m: job.set_message(tag + m))
                return {**res, "timings": {"draw": drew["draw_s"], "generate": res["total_s"]}}

            job = queue.submit(asset["id"], "generate", run)
            items.append({"asset_id": asset["id"], "prompt": words, "type": kind,
                          "job_id": job.id})
        batch_id = f"b{len(batches) + 1}-{int(time.time())}"
        batches[batch_id] = items
        return _batch_view(batch_id, items, queue)

    @app.get("/api/batch/{batch_id}")
    def batch(batch_id: str) -> dict:
        if batch_id not in batches:
            raise missing("batch")
        return _batch_view(batch_id, batches[batch_id], queue)


def _busy(queue: GpuQueue, asset_id: str) -> bool:
    """A job for this asset is queued, running, or has not finished writing its result."""
    return any(j.asset_id == asset_id and not j.settled for j in list(queue.jobs.values()))


def _batch_view(batch_id: str, items: list[dict], queue: GpuQueue) -> dict:
    out = []
    for it in items:
        job = queue.jobs[it["job_id"]]
        j = job.public()
        out.append({**it, "state": j["state"], "message": j["message"], "error": j["error"],
                    "elapsed_s": j["elapsed_s"], "ahead": queue.ahead_of(job)})
    finished = all(i["state"] in ("done", "failed") for i in out)
    return {"id": batch_id, "items": out, "finished": finished,
            "done": sum(i["state"] == "done" for i in out)}
