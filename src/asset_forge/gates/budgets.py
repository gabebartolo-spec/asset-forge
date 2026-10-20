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
            out.append(f"The report has no '{name}', so that limit cannot be checked.")
            return None
        return report[name]

    tris = need("triangles")
    if tris is not None and tris > budget.triangles:
        out.append(f"Too many triangles: {tris:,} against a limit of {budget.triangles:,}. "
                   "Decimate harder.")
    mats = need("materials")
    if mats is not None and mats != budget.materials:
        out.append(f"{mats} materials; the model must have exactly {budget.materials}. "
                   "Merge them into one.")
    tex = need("texture")
    if tex is not None:
        w, h = tex.get("width", 0), tex.get("height", 0)
        if w > budget.texture_px or h > budget.texture_px:
            out.append(f"Texture is {w}x{h}; the limit is {budget.texture_px}x{budget.texture_px}. "
                       "Use a smaller texture.")
    sil = report.get("silhouette")
    if sil:
        limit = sil.get("threshold", 0.08)
        for view in ("front", "side", "top"):
            if view in sil and sil[view] > limit:
                out.append(f"The {view} outline changed by {sil[view]:.0%} against the raw model; "
                           f"the limit is {limit:.0%}. The rebuild lost shape; try again or "
                           "raise the detail.")
    bones = report.get("bones")
    if bones is not None and bones > budget.bones:
        out.append(f"{bones} bones; the limit is {budget.bones}. Drop a bone chain.")
    infl = report.get("max_influences")
    if infl is not None and infl > budget.influences:
        out.append(f"A vertex has {infl} bone influences; the limit is {budget.influences}.")
    return out


def check_file(path: str | Path, asset_type: str, budget: Budget | None = None) -> list[str]:
    return check(json.loads(Path(path).read_text()), asset_type, budget)
