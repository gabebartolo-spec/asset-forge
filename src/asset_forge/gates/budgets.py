"""Budget checks that read the Clean step's report.json and name the broken limit in plain words.

`check(report, asset_type)` returns a list of sentences; an empty list means the model passes.
Only fields present in the report are checked, except that the Clean-step fields (triangles,
materials, texture) are required: a report without them fails with a sentence saying so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Budget:
    triangles: int
    texture_px: int
    materials: int = 1
    bones: int = 64
    influences: int = 4


BUDGETS = {
    "humanoid": Budget(8000, 1024),
    "monster": Budget(8000, 1024),
    "animal": Budget(2000, 512),
}


def check(report: dict, asset_type: str, budget: Budget | None = None) -> list[str]:
    """Plain-words list of broken limits. `budget` overrides the type default (design 6: editable
    per asset)."""
    key = asset_type.lower()
    if budget is None:
        if key not in BUDGETS:
            return [f"Unknown model type '{asset_type}'; use humanoid, monster or animal."]
        budget = BUDGETS[key]
    out: list[str] = []

    def need(name):
        if name not in report:
            out.append(f"The step's report has no '{name}', so that limit cannot be checked. "
                       "Redo runs the step again.")
            return None
        return report[name]

    tris = need("triangles")
    if tris is not None and tris > budget.triangles:
        out.append(f"Too many triangles: {tris:,} against a limit of {budget.triangles:,}, so "
                   "the model would be slow in the game. Redo runs the clean again and cuts it "
                   "down to the limit.")
    mats = need("materials")
    if mats is not None and mats != budget.materials:
        out.append(f"The model has {mats} materials (paint layers); it must have exactly "
                   f"{budget.materials}. Redo runs the clean again, which paints it as one.")
    tex = need("texture")
    if tex is not None:
        w, h = tex.get("width", 0), tex.get("height", 0)
        if w > budget.texture_px or h > budget.texture_px:
            out.append(f"Texture is {w}x{h}; the limit is {budget.texture_px}x{budget.texture_px}, "
                       "so it would use too much memory in the game. Redo runs the clean "
                       "again at the right size.")
    sil = report.get("silhouette")
    if sil:
        limit = sil.get("threshold", 0.08)
        for view in ("front", "side", "top"):
            if view in sil and sil[view] > limit:
                out.append(f"The {view} outline changed by {sil[view]:.0%} against the generated "
                           f"model (the limit is {limit:.0%}): the clean lost part of its shape. "
                           "Redo runs the clean again; if it still fails, go back to Generate "
                           "for a new model.")
    bones = report.get("bones")
    if bones is not None and bones > budget.bones:
        out.append(f"The skeleton has {bones} bones; the limit is {budget.bones}, so the game "
                   "would struggle to move it. Redo runs the skeleton step again.")
    infl = report.get("max_influences")
    if infl is not None and infl > budget.influences:
        out.append(f"Part of the skin follows {infl} bones at once (bone influences); the limit "
                   f"is {budget.influences}, or the game cannot bend it. Redo runs the skeleton "
                   "step again.")
    return out


def check_file(path: str | Path, asset_type: str, budget: Budget | None = None) -> list[str]:
    return check(json.loads(Path(path).read_text()), asset_type, budget)
