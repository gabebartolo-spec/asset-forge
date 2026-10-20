# Asset Forge: design

Date: 2026-10-19. Director: gabebartolo-spec. Written from the brainstorm on 2026-10-19.
Status: the director asked for the repo to be set up for development on 2026-10-19. The first
build step is the bake-off (section 5.2), and its result goes back to him before the app is built.

## 1. What it is, and why

A local app that turns a text prompt or a reference image into game-ready art, with no spend:

1. **3D models**: humanoids, monsters (including many-legged ones), and low-poly animals.
   Each is generated, rebuilt in Blender into a clean game mesh, given a skeleton, given a
   standard set of animations, and exported for Godot.
2. **Pokémon-style 2D sprites**: pixel-perfect (every pixel on the grid, a limited palette, no
   blurred or half-size pixels), made either straight from text or an image, or by rendering a
   model from tab 1.

The director wants this because he does not know how to model, rig or animate. He wants assets
he can drop into his games (AFL, MERCS, Southern Cross and others) without hand fixing.

**Pillar (director, 2026-10-19):** "Every asset it makes drops straight into a game:
good-looking, light to run, and fast to get."

## 2. Goals, non-goals, anti-goals

**Goals**
- Text, an image, or both, in; a rigged, animated `.glb` that imports into Godot with no errors
  out.
- A pixel-perfect sprite (front and back) ready for the target game, in about a minute.
- Every step can be reviewed and redone; a batch mode queues several prompts.

**Non-goals (v1)**
- Paid services (Tripo, Retro Diffusion, Meshy). Director chose local-only on 2026-10-19.
- Hand sculpting or painting tools. Blender stays available for that; the app saves the `.blend`.
- Facial rigs, finger bones, cloth or hair physics, blend shapes.
- Text-to-motion AI. Possible later for humanoids; not in v1.
- Running in the cloud or on another PC.

**Anti-goals: the director's three reasons he would stop using it (2026-10-19)**
1. **The models are ugly.**
2. **They are not optimised for performance.**
3. **The process is too slow.**

Each one has a measurable gate in section 6. A feature that makes any of the three worse is
rejected even if it works.

## 3. Decisions the director made (2026-10-19)

| Decision | His choice |
|---|---|
| Where generation runs | His PC, free (local models). No paid APIs. |
| What it makes | Humanoids, monsters (some many-legged), low-poly animals, Pokémon-style 2D sprites |
| How sprites are made | Both: drawn straight from text/image, and rendered from a 3D model |
| How the app flows | Step by step: one screen per step, a big viewer, Next and Redo (mockup B) |
| Animation | He cannot animate, so the tool animates. Every rigged model gets Idle, Walk and run, Attack, Hit and faint |
| Name | Asset Forge (repo `asset-forge`, skill prefix `forge-`) |
| Repo | Public on GitHub (`gabebartolo-spec/asset-forge`) |
| Pillar | The sentence in section 1 |

## 4. The machine and what already exists

- Windows 11, RTX 4070 SUPER (12 GB VRAM), 32 GB RAM, AMD CPU.
- Blender 5.2 at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`.
- ComfyUI v0.39.1 managed by Stability Matrix at
  a local folder (its path lives in `config.local.toml`, never in git; not running by default). Models already downloaded: `hunyuan3d-dit-v2-mv_fp16.safetensors`
  (Hunyuan3D 2 multi-view), `pixelArtDiffusionXL_spriteShaper.safetensors` (SDXL), LoRAs
  `pixel-art-xl-v1.1` and `Pixel_Art_Sprite_Sheet_space_candy_media`.
- **Shared-machine rules (binding):** never update, reinstall or add a second copy of the
  Stability Matrix ComfyUI, and never switch it through comfy-mcp. Anything Asset Forge needs
  installed goes in its own environment inside the repo (e.g. `.venv/`, gitignored). Blender runs
  headless (`blender -b`), never stealing focus. ComfyUI, Blender bakes and any local model share
  one GPU: one generation job at a time.
- **Licences (binding):** every model, LoRA, node pack or library must allow commercial use; the
  games are commercial. Record each in `docs/LICENCES.md` before it is used. Known flags: Flux
  dev is non-commercial (banned); Hunyuan3D 2.x is under the Tencent Hunyuan Community Licence
  (commercial use allowed, but it excludes the EU, UK and South Korea and caps very large user
  counts); TRELLIS is MIT. Name the licence of each candidate in the bake-off report.

## 5. How it works

### 5.1 Shape of the app (builder's call within these lines)

- A local web app: a Python backend that serves a page at `http://127.0.0.1:<port>`, opened by a
  double-click launcher (`AssetForge.bat`). It binds to localhost only.
- Three tabs: **3D model**, **Sprite**, **Library**.
- The backend drives three engines: the generator (ComfyUI over its HTTP API, or a dedicated
  Python env, per the bake-off), Blender (headless scripts in `blender/`), and pure-Python
  pixel processing.
- Every job writes to a project folder (`library/<asset-id>/`) holding each step's output, the
  settings used, and the seed, so any step can be redone without redoing earlier steps.
- My call (open to the builder): FastAPI backend plus a plain JS front end with three.js for the
  3D viewer. Gradio is not enough for draggable skeleton markers in 3D.

### 5.2 3D model tab: four steps, each with a spinnable viewer

**Step 1. Generate**
- Input: text, an image, or both; and a type: Humanoid, Monster or Animal.
- Text only: a local image model first draws a clean reference (front view, plain background,
  T- or A-pose for humanoids, side-on stance for animals), then the image-to-3D model runs. The
  reference is shown so the director can re-roll it before spending minutes on 3D.
- Re-roll keeps the prompt and changes the seed. Show the raw result untextured and textured.
- **Generator choice comes from a bake-off (first task, before the app is built):** the same five
  prompts (a humanoid, a spider-like monster with eight legs, a six-armed brute, a low-poly fox, a
  bird) run through every local image-to-3D model that fits 12 GB and allows commercial use
  (candidates: Hunyuan3D 2.0 / 2mv / 2mini / 2.1 with low-VRAM offload; TRELLIS v1; anything
  newer). The report gives time per model, peak VRAM, licence, and a labelled five-view render of
  each result. **The director picks the winner.** Keep the generator behind one interface so it
  can be swapped later.
- **Generator menu (director, 2026-10-20, D-018: "Choose every time"):** Step 1 shows a menu of
  every generator that passed the bake-off, on every run, in the order the director set (D-019: Hi3DGen, then TripoSG);
  the top one is preselected. Each entry shows its typical time and VRAM in plain words. Every
  listed generator must pass the Clean-step tests (Step 2) before it is listed.

**Step 2. Clean (Blender, headless)**
- Always rebuild; never just tidy. The raw mesh is dense and messy. Remesh or retopologise to a
  clean surface, decimate to the type's budget, merge loose bits, fix normals, put the origin at
  the feet and the model at real-world scale (humanoid about 1.8 m unless told otherwise), with
  the model facing glTF +Z (Blender -Y), Godot's model front (D-021).
- Smart UV unwrap, bake the generator's colour (and normal detail where it helps) onto one
  texture, one material.
- Viewer: before/after slider, triangle count, texture size.
- **Inspection (director rule, every generated model):** five views (front, back, both sides,
  three-quarter, top), untextured and textured, plus an anatomy count for creatures (heads, eyes,
  limbs, feet; no missing, fused or melted parts). The app renders this sheet automatically and
  flags loose parts and holes. Re-inspect after decimation.

**Step 3. Skeleton**
- Humanoid: a fixed humanoid template (Godot-compatible bone names so Godot's humanoid retarget
  profile maps it). The app fits the template to the mesh and shows joint markers.
- Animal: a fixed four-legged template with a tail and neck chain, fitted the same way.
- Monster: no fixed template. The app proposes a skeleton from the mesh's shape (find the body
  core and each limb from the mesh's medial axis or segmentation), counts the legs and arms, and
  shows the markers. The director drags any wrong marker, adds or removes a limb, then confirms.
- Then bind and weight (Blender automatic weights, with a fallback such as voxel heat or envelope
  when automatic weights fail on generated meshes). Maximum 4 bone influences per vertex.
- Viewer: a quick test pose so bad weights show before the animations are made.

**Step 4. Animate and export**
- Procedural animations generated in Blender from the skeleton, never from text prompts:
  - **Idle:** breathing and a slight sway, looping.
  - **Walk and run:** looping, feet planted with no sliding (IK feet driven by a gait
    generator). Two legs alternate. Four legs use a walk or trot pattern. Six or more use
    insect-style alternating groups (a tripod gait for six, a wave gait for more).
  - **Attack:** a lunge or swipe for humanoids and monsters, a bite or pounce for animals.
  - **Hit:** a short flinch. **Faint:** a collapse (Pokémon-style faint, or a death).
- Clips named `idle`, `walk`, `run`, `attack`, `hit`, `faint`, all in one `.glb`, plus the
  `.blend`.
- Export runs the performance gate (section 6) and a Godot import check (the `.glb` loads
  headless in Godot with no errors or warnings). A model that fails does not export, and the app
  says which limit it broke.
- Watch each animation in the viewer before exporting.

### 5.3 Sprite tab

**Target presets.** A preset sets size, palette limit, views and export format. v1 ships:

| Preset | Art size | Palette | Export |
|---|---|---|---|
| **Southern Cross (default)**: Essentials v21.1, Gen 9 Pack v3.3.8 | 96×96 | no fixed limit (kept clean by the QA) | front 2× (192 px), back 3× (288 px), the pack's file layout |
| GBA | 64×64 | 16 colours including transparent, indexed PNG | front + back |
| Custom | any | any limit | any views |

**Mode A: draw from text or image**
- Local SDXL with the pixel-art model and LoRAs already installed (licences checked first). It
  generates at a large size, then deterministic Python post-processing makes it pixel-perfect:
  detect the true pixel grid and downsample on it (no smoothing), cut the background to
  transparent, reduce to the preset's palette, add or repair a one-pixel dark outline, remove
  stray single pixels and holes, and keep the sprite 2 px clear of the canvas edge.
- The back view is a real view from behind (director rule, 2026-10-19): a different silhouette,
  showing the back and rump with the face hidden, never the front with the face erased. Prompt
  it as an explicit turned pose, and reject a back whose outline mostly overlaps the front's (or
  its mirror).

**Mode B: render from a 3D model**
- Pick a model from the Library. Blender renders it orthographic at the preset's size with no
  anti-aliasing, flat or toon shading, and a fixed three-quarter front and three-quarter back
  camera like the Pokémon battle views. The same palette and outline clean-up as mode A follows.
- Optional: render an animation clip (idle) as frames for an animated sprite.

**Sprite QA (automatic, before the director sees it):** no unoutlined edge pixel, no stray
pixels, no holes or leftover background, within the palette limit, 2 px clear of the edge, and
the back-view silhouette check. Show the result at 1× and at 4×–8× on a grid.

### 5.4 Library

Every asset with its thumbnail, type, date and the step it reached. Open one to resume at any
step, duplicate it, or delete it (moved to `library/_trash/`, not erased). Exports go to
`exports/<asset-id>/`.

### 5.5 Batch mode

Queue several prompts with types; the app runs them one after another through Generate and
Clean, then stops at Skeleton for each, because the skeleton check needs the director. Humanoids
and animals with a confident template fit can optionally run straight through.

### 5.6 Optional local-AI QA check (director, 2026-10-20, D-015; built after a working build)

- A setting, off by default: "Ask a local AI to check the model". When on, after Clean (and after
  any fix) the app loads a local vision model (through Ollama), shows it the five-view sheet and
  asks about missing, fused or melted parts and facing. Then it unloads the model (one GPU).
- Result: a short plain-words note on the step screen ("Looks clean" / "Back left leg looks fused
  to the body"), with the view marked. It warns only; it never blocks export or changes the model.
  The measured checks (section 6) stay the gate.
- The model needs a CLEARED row in `docs/LICENCES.md`. Its agreement with the critic agents'
  verdicts is measured on saved sheets before it ships; if it mostly raises false alarms, it stays off.

### 5.7 Claude MCP server (director, 2026-10-20, D-016; roadmap Phase 8)

- A local MCP server so Claude Code can operate Asset Forge: create a job from text or an image,
  run or redo any step, read the five-view sheet and gate results, move skeleton markers, export,
  make sprites, and browse the Library.
- A thin layer over the backend's job API (the same calls the page makes), localhost only, through
  the one GPU queue. Every step keeps its saved output, so Claude's work is resumable in the UI.
- Builder's note from now: keep every step callable through the backend API, never only from the page.
- The MCP SDK gets a `docs/LICENCES.md` row before use.

## 6. Gates (how the anti-goals are measured)

**Not ugly**
- The bake-off winner is the director's pick (section 5.2).
- After Clean, the silhouette from front, side and top must stay within a set difference of the
  raw model (the builder picks the measure and the threshold, and reports both).
- Every model passes the five-view inspection; every sprite passes the sprite QA.

**Optimised (hard limits, checked on export)**

| Limit | Humanoid / Monster | Low-poly animal |
|---|---|---|
| Triangles | ≤ 8,000 | ≤ 2,000 |
| Bones | ≤ 64 | ≤ 64 |
| Materials | 1 | 1 |
| Texture | ≤ 1024×1024 | ≤ 512×512 |
| Bone influences per vertex | ≤ 4 | ≤ 4 |

Defaults are editable per asset, but the export always checks against the asset's own budget.
Every export loads in headless Godot with no errors.

**Fast (targets, measured on this PC and reported)**
- 3D: prompt to rigged, animated `.glb` in about 5 minutes of machine time and about 1 minute of
  the director's clicks.
- Sprite: under 1 minute.
- The app shows each step's time, so slow steps are visible.

**Clean and intuitive (director, 2026-10-20, D-013)**
- One main action per screen, plainly labelled; Next and Redo always in the same place.
- No setting on the main path that the defaults already answer; advanced options folded away.
- Built for a normal person with no advanced tech skills (director, 2026-10-20, D-014): plain
  words on screen, no jargon on the main path (VRAM use is shown: he asked for it), every error
  names the one click that fixes it.
- Every screen passes a fresh `screen-critic` review and a first-use walk-through (a new agent
  reaches the step's goal from the screen alone, no docs) before the director sees it.

## 7. Quality and process

- Tests: pure-Python parts (pixel processing, gates, the job store) get unit tests; Blender
  scripts get headless integration tests on a tiny fixture mesh; generation is mocked in CI (no
  GPU there). CI must stay quick (10–12 minutes at most) and run lint (ruff), tests (pytest),
  doc size caps and a secret scan (gitleaks).
- The repo is public: no keys, tokens, personal paths in committed config (paths come from a
  local, gitignored `config.local.toml` with documented defaults), and no model weights.
- Visual results reach the director only after the lead's own check (zoomed crops, five views,
  both front and back sprites) under the `art-qa-critic` skill.

## 8. Left to the builder

- The exact libraries (backend framework, viewer, retopology method, medial-axis method, grid
  detection), as long as they are free for commercial use and fit the gates.
- The silhouette measure and threshold, and the auto-skeleton algorithm for monsters.
- The procedural gait details, as long as feet do not slide and the gaits named above are used.
- The order of work after the bake-off. Suggested: bake-off → Generate + Clean → export gate and
  Godot check → Skeleton (humanoid, animal, then monster) → animations → Sprite mode A → Sprite
  mode B → Library and batch.

## 9. Answers after the builder check (2026-10-19)

**Director's answer**
- **Default sprite preset: Southern Cross** (Essentials v21.1, Gen 9 Pack v3.3.8): 96×96 art, no
  16-colour limit, exported scaled into the pack's frames (front 2× = 192 px, back 3× = 288 px).
  GBA stays a one-click preset. Match the pack's existing sprite files (frame layout, naming,
  animated strips) by reading `../pokemon-southern-cross` before writing the exporter.

**Lead's calls (the director may overrule any)**
- **Budget for many-limbed monsters:** 8,000 triangles stays the default; the budget is editable
  per asset. If the bake-off shows 8k ruins a spider's legs, report it with renders and propose a
  number; do not raise it silently.
- **Monster skeleton in v1:** ship a limb-chain editor first (the app proposes a body core; the
  director clicks to add or remove leg and arm chains and drags joints). Automatic limb detection
  is an assist layered on later, not a blocker for v1.
- **A gate fails:** no automatic re-seed. The app names the broken limit and offers one-click
  fixes (decimate harder, smaller texture, drop a bone chain) and re-runs only the failed step.
- **Godot:** 4.7.2, the version the other projects pin. Bone names follow Godot's
  `SkeletonProfileHumanoid` for humanoids. The import check runs Godot headless on the `.glb`.
  The Godot path comes from `config.local.toml`.
- **Bake-off bar:** a candidate qualifies if it fits in 12 GB, has a commercial-use licence,
  takes ≤ 3 minutes per model, and passes the five-view inspection on at least 3 of the 5
  prompts. The director picks among qualifiers from labelled renders.
- **Hunyuan licence:** the director is in Australia, outside the excluded territories, so
  Hunyuan models may enter the bake-off. Record the licence terms in `docs/LICENCES.md`.
- **One GPU:** a single job queue in the backend; before a Blender bake or render, the app frees
  ComfyUI's VRAM (its `/free` endpoint) rather than shutting ComfyUI down.
