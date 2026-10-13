"""Open the Meridian proposal tool in a browser and feed it a proposal via window.loadProposal."""
from __future__ import annotations

import os
from pathlib import Path


def tool_path(pack_dir: str | Path | None = None) -> Path:
    pack = Path(pack_dir or os.getenv("PACK_DIR", "meridian-ai-challenge"))
    html = pack / "challenge-generator.html"
    if not html.exists():
        raise FileNotFoundError(
            f"Could not find {html}. Unzip the challenge pack next to this project "
            "(so meridian-ai-challenge/challenge-generator.html exists) or set PACK_DIR."
        )
    return html.resolve()


def load_into_tool(
    proposal: dict,
    pack_dir: str | Path | None = None,
    *,
    headless: bool = False,
    preview: bool = False,
    screenshot: str | Path | None = None,
    wait: bool = True,
) -> str:
    """Load `proposal` into the tool. Returns the id of the new proposal.

    headless=False  -> a visible browser window opens so the PM can review/tweak
    preview=True    -> start on the rendered preview instead of the editor
    screenshot=path -> save a PNG after loading (handy for the demo / README)
    wait=True       -> keep the window open until the PM closes it
    """
    from playwright.sync_api import sync_playwright

    url = tool_path(pack_dir).as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_function("typeof window.loadProposal === 'function'")
        proposal_id = page.evaluate(
            "([p, o]) => window.loadProposal(p, o)", [proposal, {"preview": preview}]
        )
        page.wait_for_timeout(400)  # let the tool finish rendering
        if screenshot:
            Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot))
        if wait and not headless:
            print("Proposal loaded. Review/tweak it in the browser; close the window to exit.")
            page.wait_for_event("close", timeout=0)
        browser.close()
    return proposal_id
