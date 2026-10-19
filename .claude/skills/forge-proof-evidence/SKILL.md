---
name: forge-proof-evidence
description: How to prove a change to Asset Forge actually works before calling it done - the evidence that fits each kind of change (pipeline step, gate, Blender script, sprite processing, UI), real clicks in the page instead of handler calls, proving the asset the step really produced, Godot import checks, five-view inspections, new checks shown failing first, and the Not exercised line. Extends the general afl-proof-evidence ideas and art-qa-critic. Use it when finishing any feature or fix, writing a PR's Evidence section, adding a test, or about to say something works or looks right.
---

# Proof before "done"

"It works" is not evidence; what the tool produced is. The usual false passes: a test that calls
an endpoint while the page's button is broken, a render of the raw mesh instead of the cleaned
one, a gate tested only on a model that was already inside budget, a sprite QA that never saw a
bad sprite.

## Pick evidence that fits the change

| Change | Evidence that counts |
|---|---|
| Pure Python (gates, pixel processing, job store) | unit tests, each new check shown failing on a known-bad input first |
| Blender script (clean, rig, animate, render) | `pytest -m blender` on the fixture mesh; numbers before/after (tris, bones, materials, texture size) |
| Export | the `.glb` imports in headless Godot 4.7.2 with no errors or warnings; the gate report |
| Generator / bake-off | per-prompt time and peak VRAM; five-view sheet untextured and textured; anatomy count |
| Animation | a short clip per clip name (idle, walk, run, attack, hit, faint); feet do not slide |
| Sprite | 1x and 4-8x on a grid; sprite QA report; front and back side by side (back is a real back view) |
| UI flow | a real click at the control's position in the page (browser automation), then the result on screen |

## A look is the director's

Validators and green tests never approve a look. The lead's `art-qa-critic` and `ai-slop-art`
pass first (2x crops, five views), then the director from labelled images (a clip for motion).

## Write it down

**Evidence:** tests with counts, fixture, seed, capture or clip by path. **Not exercised:** what
you did not cover. After two similar failed fixes, change the evidence before another fix.

## Learnings

Proven findings for this project live in `references/learnings.md`; general ones go to the
general skill's log.
