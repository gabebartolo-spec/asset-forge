# Licence register

Cap: 200 lines. Nothing is used until it has a row here with verdict CLEARED. Commercial use is
required; non-commercial, research-only or unclear licences are BANNED. HELD = cleared on paper
but waiting on a director decision. Checked 2026-10-20 from primary sources (licence files,
HF model cards); VRAM is from READMEs until the bake-off measures it. Not legal advice.

## Image-to-3D candidates

| Item | Kind | Licence | Verdict | Notes |
|---|---|---|---|---|
| Hunyuan3D 2.0 / 2mv (`hunyuan3d-dit-v2-mv`) / 2mini | image-to-3D | Tencent Hunyuan 3D 2.0 Community | BANNED (D-010) | §5(c): no use or distribution of Output outside the Territory (world minus EU, UK, South Korea); >1M MAU needs a grant; outputs may not train other models; Tencent claims no rights in outputs (§6d). Shape ~6 GB |
| Hunyuan3D 2.1 | image-to-3D | Tencent Hunyuan 3D 2.1 Community | BANNED (D-010) | same terms as 2.0; shape ~10 GB, texture ~21 GB (needs a separate pass on 12 GB) |
| TripoSG (VAST-AI) | image-to-3D | MIT | CLEARED | ≥8 GB; geometry only; replace its default RMBG-1.4 matting with BiRefNet |
| TripoSR | image-to-3D | MIT | CLEARED | ~6 GB; older, coarse; HF card `stabilityai/TripoSR` MIT (2026-10-20) |
| Hi3DGen / Stable3DGen | image-to-3D | MIT | CLEARED | TRELLIS fork with the non-commercial deps removed (no nvdiffrast/diffoctreerast/FlexiCubes, grepped); geometry only; weights `Stable-X/trellis-normal-v0-1` MIT, normals `Stable-X/yoso-normal-v1-8-1` (StableNormal) Apache-2.0 (HF cards, 2026-10-20) |
| Step1X-3D | image-to-3D | Apache-2.0 | CLEARED | 27-29 GB with texture; geometry-only may fit with offload; reuses Hunyuan rasteriser code (Tencent terms on that code) |
| Direct3D-S2 | image-to-3D | MIT | CLEARED | weights `wushuang98/Direct3D-S2` MIT (HF card, 2026-10-20); flash-attn replaced by an SDPA shim; torchsparse MIT, triton-windows MIT |
| Stable Fast 3D (SF3D), SPAR3D | image-to-3D | Stability AI Community | CLEARED | free below US$1M annual revenue, Enterprise licence above; ~6 GB; gated HF weights |
| TRELLIS (image-large weights MIT) | image-to-3D | MIT + non-commercial deps | BANNED | GLB export needs nvdiffrast, diffoctreerast, FlexiCubes; README asks 16 GB |
| TRELLIS.2-4B | image-to-3D | MIT + non-commercial deps | BANNED | 24 GB; nvdiffrast/nvdiffrec, DINOv3 |

## Image models and LoRAs (sprites, reference images)

| Item | Kind | Licence | Verdict | Notes |
|---|---|---|---|---|
| SDXL 1.0 base | image model | CreativeML Open RAIL++-M | CLEARED | use restrictions follow outputs |
| `pixel-art-xl-v1.1` (nerijs) | LoRA | CreativeML OpenRAIL-M | CLEARED | |
| `pixelArtDiffusionXL_spriteShaper` | SDXL checkpoint | none named; creator forbids selling images without written consent | BANNED | |
| `Pixel_Art_Sprite_Sheet_space_candy_media` | LoRA | unknown (Civitai region-blocked here) | BANNED | flags unreadable; revisit only if needed |
| Flux dev | image model | non-commercial | BANNED | |

## Libraries, node packs, helpers

| Item | Kind | Licence | Verdict | Notes |
|---|---|---|---|---|
| Blender 5.2 | tool | GPL-3.0 (outputs are ours) | CLEARED | |
| Godot 4.7.2 | tool | MIT | CLEARED | export checks only |
| BiRefNet | matting model | MIT | CLEARED | `trust_remote_code`: pin revision `e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4` |
| kaolin | library | Apache-2.0 | CLEARED | |
| ComfyUI-Hunyuan3DWrapper (kijai) | node pack | Tencent Hunyuan 3D 2.0 Community | BANNED (D-010) | follows Hunyuan; confirm no pip dep pulls nvdiffrast |
| ComfyUI-3D-Pack | node pack | MIT, aggregates non-commercial deps | BANNED | |
| ComfyUI-IF_Trellis, ComfyUI-Trellis2 / TRELLIS2 | node pack | MIT + non-commercial deps | BANNED | |
| nvdiffrast, nvdiffrec | library | NVIDIA Source Code (non-commercial) | BANNED | §3.3 |
| diffoctreerast, mip-splatting, diff-gaussian-rasterization | library | Inria/MPII Gaussian-Splatting (research) | BANNED | |
| DINOv2 (`facebook/dinov2-with-registers-large`, `dinov2-large`, torch hub vitl14_reg) | image encoder | Apache-2.0 | CLEARED | used inside TripoSG, Step1X-3D, Hi3DGen, Direct3D-S2; DINO v1 `facebook/dino-vitb16` (TripoSR) also Apache-2.0 (HF cards, 2026-10-20) |
| diso (DiffDMC / FlexiCubes) | library | CC BY-NC 4.0 | BANNED | non-commercial; TripoSG imports it, our adapter stubs it out and uses scikit-image marching cubes |
| NVIDIA CUDA runtime + NVRTC wheels (`nvidia-cuda-runtime-cu12`, `nvidia-cuda-nvrtc-cu12`) | runtime DLLs | NVIDIA CUDA Toolkit EULA | CLEARED | redistributable runtime components; used by spconv in the Hi3DGen env only, never committed |
| torchmcubes | library | MPL-2.0 | CLEARED | TripoSR marching cubes, built locally with CUDA; we do not modify its files |
| spconv (`spconv-cu126`) | library | Apache-2.0 | CLEARED | Hi3DGen sparse convolutions |
| xformers | library | BSD-3-Clause | CLEARED | Hi3DGen attention |
| torchsparse | library | MIT | CLEARED | Direct3D-S2, patched and built locally |
| triton-windows | library | MIT | CLEARED | Direct3D-S2 |
| trimesh, fast-simplification, scikit-image | library | MIT, MIT, BSD-3-Clause | CLEARED | mesh I/O, Step1X-3D cleanup, marching cubes |
| peft, diffusers, huggingface_hub | library | Apache-2.0 | CLEARED | SDXL + LoRA draw step in `models/envs/sdxl` (sprite mode A); PyPI metadata 2026-10-20 |
| numpy, Pillow | library | BSD-3-Clause, MIT-CMU (HPND) | CLEARED | sprite post-processing; app dependencies |
| RMBG-1.4 / 2.0 (Bria) | matting model | bria-rmbg (non-commercial) | BANNED | |
| DINOv3 | model | Meta dinov3-license | BANNED until read | TRELLIS.2 only |

## Prompt generator (Phase 9, D-020)

| Item | Kind | Licence | Verdict | Notes |
|---|---|---|---|---|
| Qwen3-1.7B (`Qwen/Qwen3-1.7B`) | text LLM | Apache-2.0 | CLEARED | HF card `license: apache-2.0` (API, 2026-10-20); about 3.4 GB in bf16; Qwen2.5-3B is NOT Apache (Qwen research licence), so not used |
| transformers, huggingface_hub, accelerate | library | Apache-2.0 | CLEARED | run only in `models/envs/promptgen`, never imported by the app |
| PyTorch | library | BSD-3-Clause | CLEARED | same env |
