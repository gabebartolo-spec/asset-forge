# ref-drawer handoff (branch claude/ref-drawer, no PR opened; the lead opens it)

State: code, tests and real evidence done; pushed. Open question to the lead: background cut (below).

## PR body draft

### What
Text-only input now draws a real reference. `SdxlReferenceDrawer` (src/asset_forge/draw.py) runs
SDXL 1.0 base (no LoRA) in models/envs/sdxl through `src/asset_forge/refdraw_worker.py`, one
short-lived process per draw (loads, draws 1024x1024, exits: VRAM freed). Prompt = the user's words +
a per-type view (humanoid A-pose front; monster three-quarter front, every limb visible; animal
side view facing left, bird included) + the bake-off style/negative (tools/bakeoff/prompts.toml).
`default_drawer` returns it when models/envs/sdxl and the SDXL weights exist, else
`UnavailableDrawer` with the same plain note as before. No GPU lock taken in the drawer: it runs
inside a queue job, which already holds models/gpu.lock (taking it again would deadlock).

### Evidence
- tests/test_ref_drawer.py (7 tests): shown failing first (ImportError before the code), now green;
  prompt per type, types differ, unknown type error, runner error passes through, fallback with no
  weights, available with weights. Full suite 189 passed (minus blender marker), ruff clean.
- Real run, five bake-off prompts, seed 7, 30 steps, cfg 6.0, via the drawer itself under the GPU
  lock: seconds per picture (process start + load + draw) 56.4 (first, cold), 33.5, 34.4, 35.1,
  32.2; peak VRAM 10736 MB (fits 12 GB, little headroom). PNGs, cut-outs, sheet_a/sheet_b.png and
  timing.json in side-session-notes/local_7fdc3e78-.../ref_drawer/.
- Looked at at 2x (sheet): humanoid OK (one knight, whole body; holds a sword, arms near A-pose);
  spider OK (8 legs, one subject); brute FAIL (2 huge arms, not 6); fox FAIL (one good low-poly fox
  plus two small stray foxes below: multiple subjects); bird PARTIAL (robin on a branch with one
  wing raised, not wings folded). Limb counts (brute 6 arms) are not controlled by SDXL base at this
  prompt; no fix invented.
- Background: SDXL draws a grey vignette, not flat white. The app's matte.prepare_reference
  (flood from the border, tolerance 28) therefore leaves grey blobs around every subject
  (sheet_b.png). The 3D step would see grey patches.

### Not exercised
Through the app page (real click Draw); batch path; other seeds; BiRefNet matting in the drawer
(not built: out of brief).

### Board and log
STATUS: text-only drawing exists (item 4 follow-up). Open: background cut-out quality, brute 6 arms.

### MERGE NOTE
Touches draw.py only plus the new worker; no overlap expected. Needs models/envs/sdxl on the machine.
