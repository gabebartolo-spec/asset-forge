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
| TripoSR | image-to-3D | MIT | CLEARED | ~6 GB; older, coarse |
| Hi3DGen / Stable3DGen | image-to-3D | MIT | CLEARED (provisional) | TRELLIS fork with the non-commercial deps removed; geometry only; recheck HF weights licence before use |
| Step1X-3D | image-to-3D | Apache-2.0 | CLEARED | 27-29 GB with texture; geometry-only may fit with offload; reuses Hunyuan rasteriser code (Tencent terms on that code) |
| Direct3D-S2 | image-to-3D | MIT | CLEARED (provisional) | VRAM and dependencies unchecked |
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
| BiRefNet | matting model | MIT | CLEARED | |
| kaolin | library | Apache-2.0 | CLEARED | |
| ComfyUI-Hunyuan3DWrapper (kijai) | node pack | Tencent Hunyuan 3D 2.0 Community | BANNED (D-010) | follows Hunyuan; confirm no pip dep pulls nvdiffrast |
| ComfyUI-3D-Pack | node pack | MIT, aggregates non-commercial deps | BANNED | |
| ComfyUI-IF_Trellis, ComfyUI-Trellis2 / TRELLIS2 | node pack | MIT + non-commercial deps | BANNED | |
| nvdiffrast, nvdiffrec | library | NVIDIA Source Code (non-commercial) | BANNED | §3.3 |
| diffoctreerast, mip-splatting, diff-gaussian-rasterization | library | Inria/MPII Gaussian-Splatting (research) | BANNED | |
| RMBG-1.4 / 2.0 (Bria) | matting model | bria-rmbg (non-commercial) | BANNED | |
| DINOv3 | model | Meta dinov3-license | BANNED until read | TRELLIS.2 only |
