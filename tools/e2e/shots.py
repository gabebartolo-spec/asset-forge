"""Real-click screenshots of every step's page for one model (headless Chromium, 1920x1080).

    python tools/e2e/shots.py IMAGE OUT_DIR [--url http://127.0.0.1:7860] [--type Humanoid]
        [--generator Hi3DGen] [--timeout-min 30]

Clicks exactly what a person clicks: choose the picture, the type, the generator, then the
bottom-right main button through Make 3D model, Next, Clean up, Next, Build skeleton, the two
skeleton toggles, Next, Make animations and Export for Godot. Saves a shot after each result
(OUT_DIR/NN_<what>.png) and prints the page's note line after each. The GPU work goes through
the app's own queue, so it waits behind any other job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--type", default="Humanoid")
    ap.add_argument("--generator", default="Hi3DGen")
    ap.add_argument("--timeout-min", type=float, default=30)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    wait_ms = int(a.timeout_min * 60_000)
    n = [0]
    log = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda e: log.append(f"page error: {e}"))

        def shot(what: str) -> None:
            n[0] += 1
            page.wait_for_timeout(1500)  # the viewer finishes loading and framing the model
            path = a.out / f"{n[0]:02d}_{what}.png"
            page.screenshot(path=str(path))
            note = page.locator("#note").inner_text() if page.locator("#note").is_visible() else ""
            log.append(f"{path.name}: next='{page.locator('#next').inner_text()}' note='{note}'")
            print(log[-1], flush=True)

        def press_next(expect: str) -> bool:
            """Click the main button, then wait for the label that follows success, or for an
            error note (a failed job). Returns True on success."""
            page.locator("#next").click()
            page.wait_for_function(
                "(want) => { const b = document.getElementById('next');"
                " const n = document.getElementById('note');"
                " return (want === '' ? !document.getElementById('export-done')"
                "   .classList.contains('hidden') : b.textContent.includes(want))"
                "   || n.classList.contains('error'); }", arg=expect, timeout=wait_ms)
            return "error" not in (page.locator("#note").get_attribute("class") or "")

        page.goto(a.url)
        page.wait_for_selector("#generators button")
        shot("step1_empty")
        page.locator("#file").set_input_files(str(a.image))
        page.get_by_role("radio", name=a.type).click()
        page.locator("#generators button", has_text=a.generator).click()
        shot("step1_ready")
        ok = press_next("Next: Clean up")
        shot("step1_model")
        if ok:
            ok = press_next("Clean up")  # Next -> Step 2
            shot("step2_before_clean")
        if ok:
            ok = press_next("Next: Skeleton")
            shot("step2_cleaned")
            before = page.locator("#clean-view button[data-value=before]")
            if before.is_visible():
                before.click()
                shot("step2_before_view")
                page.locator("#clean-view button[data-value=after]").click()
        if ok:
            ok = press_next("Build skeleton")  # Next -> Step 3
            shot("step3_before_build")
        if ok:
            ok = press_next("Next: Animate")
            shot("step3_skeleton_bones")
            pose = page.locator("#tog-pose")
            if pose.is_visible():
                pose.click()
                page.wait_for_timeout(2500)
                shot("step3_test_pose")
        if ok:
            ok = press_next("Make animations")  # Next -> Step 4
            shot("step4_before_animate")
        if ok:
            ok = press_next("Export for Godot")
            shot("step4_animated_walk")
            for clip in ("Idle", "Attack"):
                b = page.locator("#clips button", has_text=clip)
                if b.is_visible():
                    b.click()
                    shot(f"step4_clip_{clip.lower()}")
        if ok:
            ok = press_next("")
            shot("step4_exported")
        page.locator("#tab-lib").click()
        page.wait_for_timeout(1500)
        shot("library")
        browser.close()
    (a.out / "shots_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
