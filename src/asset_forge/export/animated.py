"""Export the animated model (Step 4): measure the final .glb against the asset's budget
(design section 6), run the headless Godot checks, and only then copy it into exports/<asset-id>/.

The gate reads the file that ships, never a report about it: triangles, materials, the largest
texture (from the image itself), bones and bone influences per vertex. The Godot checks are the
rig check (one skeleton, skinned, <= 4 weights, <= 64 bones, humanoid profile) and a real editor
import with the loop sidecar, proving idle, walk and run loop in a game project.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from PIL import Image

from asset_forge.animate.clips import CLIP_NAMES, LOOPING
from asset_forge.export import godot_check
from asset_forge.export.exporter import ExportRefused
from asset_forge.skeleton.glb import _load, read_skin

# design section 6 (hard limits, checked on export)
BUDGETS = {
    "humanoid": {"triangles": 8000, "texture_px": 1024},
    "monster": {"triangles": 8000, "texture_px": 1024},
    "animal": {"triangles": 2000, "texture_px": 512},
}
COMMON = {"bones": 64, "materials": 1, "influences": 4}
KIND_WORDS = {"humanoid": "a humanoid", "monster": "a monster", "animal": "an animal"}


def budget_for(asset_type: str, override: dict | None = None) -> dict:
    return {**COMMON, **BUDGETS[asset_type], **(override or {})}


def measure_glb(path: Path) -> dict:
    """What the file really holds: triangles, materials, largest texture side, bones, the most
    bone influences on one vertex."""
    gltf, blob = _load(Path(path))
    tris = 0
    used_materials = set()
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                tris += gltf["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += gltf["accessors"][prim["attributes"]["POSITION"]]["count"] // 3
            if "material" in prim:
                used_materials.add(prim["material"])
    tex = 0
    for img in gltf.get("images", []):
        if "bufferView" in img:
            bv = gltf["bufferViews"][img["bufferView"]]
            off = bv.get("byteOffset", 0)
            data = blob[off:off + bv["byteLength"]]
            with Image.open(io.BytesIO(data)) as im:
                tex = max(tex, *im.size)
        elif "uri" in img and not img["uri"].startswith("data:"):
            with Image.open(Path(path).parent / img["uri"]) as im:
                tex = max(tex, *im.size)
    skin = read_skin(Path(path))
    materials = max(len(used_materials), len(gltf.get("materials", [])))
    return {"triangles": tris, "materials": materials,
            "texture_px": tex, "bones": skin.bones, "influences": skin.max_influences}


def gate_problems(m: dict, asset_type: str, budget: dict | None = None) -> list[str]:
    """Every limit the measured model breaks, in plain words (empty = passes)."""
    b = budget_for(asset_type, budget)
    kind = KIND_WORDS[asset_type]
    out = []
    if m["triangles"] > b["triangles"]:
        out.append(f"The model has {m['triangles']:,} triangles; the limit for {kind} is "
                   f"{b['triangles']:,}.")
    if m["materials"] > b["materials"]:
        out.append(f"The model uses {m['materials']} materials; the limit is {b['materials']}.")
    if m["texture_px"] > b["texture_px"]:
        out.append(f"The texture is {m['texture_px']} pixels across; the limit for {kind} is "
                   f"{b['texture_px']}.")
    if m["bones"] > b["bones"]:
        out.append(f"The skeleton has {m['bones']} bones; the limit is {b['bones']}.")
    if m["influences"] > b["influences"]:
        out.append(f"Some parts of the model follow {m['influences']} bones at once; the limit "
                   f"is {b['influences']}.")
    return out


def export_animated(anim_dir: Path, asset_id: str, asset_type: str,
                    exports_dir: Path | None = None, godot_exe: Path | None = None,
                    budget: dict | None = None) -> tuple[Path, dict]:
    """Gate and check anim_dir/animated.glb, then copy it with its loop sidecar, .blend and
    clips.json to exports/<asset_id>/<asset_id>.*. Returns (folder, report). Raises
    ExportRefused with every broken limit in plain words; nothing is copied then."""
    anim_dir = Path(anim_dir)
    glb = anim_dir / "animated.glb"
    if not glb.is_file():
        raise ExportRefused(["There are no animations to export yet. Press Animate first."])
    clips_path = anim_dir / "clips.json"
    clips = json.loads(clips_path.read_text(encoding="utf-8")) if clips_path.is_file() else {}
    try:
        m = measure_glb(glb)
    except (OSError, ValueError, KeyError) as e:
        raise ExportRefused([f"The animated file could not be read ({e}). Press Animate "
                             "again."]) from None
    reasons = gate_problems(m, asset_type, budget)
    side = godot_check.write_loop_sidecar(glb, LOOPING)
    humanoid = clips.get("template", asset_type) == "humanoid"
    rig = godot_check.check_rig(glb, exe=godot_exe, humanoid=humanoid)
    loops = {n: godot_check.LOOP_LINEAR if n in LOOPING else godot_check.LOOP_NONE
             for n in CLIP_NAMES}
    imp = godot_check.check_import(glb, loops, exe=godot_exe)
    for res in (rig, imp):
        reasons += [f"Godot could not load the model cleanly: {p}" for p in res.problems]
    report = {"measured": m, "budget": budget_for(asset_type, budget), "godot_rig": rig.summary,
              "godot_import": imp.summary, "problems": reasons}
    if reasons:
        raise ExportRefused(reasons)
    dest = (exports_dir or Path("exports")) / asset_id
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, dest / f"{asset_id}.glb")
    shutil.copy2(side, dest / f"{asset_id}.glb.import")
    for src, name in ((anim_dir / "animated.blend", f"{asset_id}.blend"),
                      (clips_path, f"{asset_id}.clips.json")):
        if src.is_file():
            shutil.copy2(src, dest / name)
    (dest / f"{asset_id}.export.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return dest, report
