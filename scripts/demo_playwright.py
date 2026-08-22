"""Presenter-controlled Playwright walkthrough of the live D3 creative-studio demo.

Drives a headed browser through the four-brief flow served by ``scripts/demo_server.py``.
It is **paced by the presenter**: before each step it prints what is about to happen and
waits for you to press Enter, then performs the action (click "Next") and highlights the
panel to look at. You stay in control.

Usage (two terminals)::

    # terminal 1 - the live demo server
    make demo-server                                    # or: MKT_CREATIVE_PROFILE=local \\
                                                          #   PYTHONPATH=src .venv/bin/python \\
                                                          #   scripts/demo_server.py

    # terminal 2 - the guided walkthrough (a real Chrome window opens)
    .venv/bin/pip install playwright && .venv/bin/playwright install chromium  # one-time
    .venv/bin/python scripts/demo_playwright.py

Point it at the real Next.js console instead with ``DEMO_URL=http://localhost:3000`` (then
it just opens the console for the presenter; the Next/Restart buttons are specific to the
demo server, so against the live console use it as a guided narration overlay).

Environment overrides:
    DEMO_URL    server base URL (default http://127.0.0.1:8112)
    HEADLESS=1  run headless (used for the self-test; no window)
    DEMO_AUTO=1 don't wait for Enter - advance automatically (self-test / recording)
    SLOWMO_MS   per-action slow-motion in ms (default 250 headed, 0 headless)
    CHROME_PATH explicit Chromium/Chrome binary (else Playwright's own)
"""

from __future__ import annotations

import contextlib
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DEMO_URL", "http://127.0.0.1:8112")
HEADLESS = os.environ.get("HEADLESS") == "1"
AUTO = os.environ.get("DEMO_AUTO") == "1"
SLOWMO = int(os.environ.get("SLOWMO_MS", "0" if HEADLESS else "250"))
CHROME_PATH = os.environ.get("CHROME_PATH") or None

# (narration shown in the terminal, whether this step clicks "Next", panel to spotlight)
STEPS = [
    (
        "The console opens on a Singapore banking email: 'high-yield savings' at 4.10% "
        "p.a. Every copy variant already carries its brand-guideline and per-market claim "
        "check, and the HUMAN REVIEW REQUIRED banner gates the set before anything ships.",
        False,
        ".variant",
    ),
    (
        "Next is a Japan banking push notification for a multi-currency wallet (12 "
        "currencies). Any variant that trips a brand or claim rule shows its finding here, "
        "severity and message, not a silent rewrite.",
        True,
        ".finding",
    ),
    (
        "An Australia online-retail social post for a spring apparel sale (20% off) is the "
        "one scenario generated with an image: the note shows the asset and aspect ratio "
        "alongside the copy so the reviewer checks both together.",
        True,
        ".variant",
    ),
    (
        "A Japan online-retail loyalty-points email (5% back) closes the walkthrough. Every "
        "variant across all four briefs traces back to the brand-guideline source it was "
        "checked against.",
        True,
        ".cites",
    ),
]


def _pause(prompt: str) -> None:
    if AUTO:
        time.sleep(1.2)
        return
    try:
        input(prompt)
    except EOFError:  # non-interactive stdin
        time.sleep(1.0)


def _spotlight(page, selector: str | None) -> None:
    if not selector:
        return
    with contextlib.suppress(Exception):  # cosmetic only
        page.eval_on_selector_all(
            selector,
            "els => els.forEach((e,i)=>{ if(i<6){ e.style.transition='box-shadow .3s';"
            " e.style.boxShadow='0 0 0 3px #3a60f0'; setTimeout(()=>e.style.boxShadow='',1600);} })",
        )


def _reachable() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(BASE + "/", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def main() -> int:
    if not _reachable():
        print(f"Cannot reach the demo server at {BASE}.")
        print("Start it first:  make demo-server")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOWMO, executable_path=CHROME_PATH)
        page = browser.new_context(viewport={"width": 1100, "height": 900}).new_page()

        print("\n=== D3 creative-studio live demo - press Enter to advance each step ===\n")
        page.goto(BASE + "/restart", wait_until="load")  # always start clean
        page.goto(BASE + "/", wait_until="load")

        for i, (say, click, spotlight) in enumerate(STEPS):
            print(f"[{i + 1}/{len(STEPS)}] {say}")
            _pause("        press Enter to run this step... ")
            if click:
                btn = page.locator(".democtl button.next")
                if btn.count() and btn.is_enabled():
                    btn.click()
                    page.wait_for_load_state("load")
            page.wait_for_timeout(200)
            _spotlight(page, spotlight)
            page.wait_for_timeout(700)
            print()

        print("Demo complete. The browser stays open for questions.")
        _pause("        press Enter to close the browser... ")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
