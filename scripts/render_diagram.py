#!/usr/bin/env python3
"""Screenshot the Persian architecture diagram HTML to PNG via Playwright."""
import asyncio
import os
from playwright.async_api import async_playwright

HTML = "/home/z/my-project/scripts/architecture_diagram.html"
OUT = "/home/z/my-project/download/architecture_diagram_fa.png"


async def html_to_image(html_path, output_path, selector="#root", width=1320, scale=2):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": width, "height": 900},
            device_scale_factor=scale,
        )
        await page.goto(f"file://{html_path}", wait_until="networkidle")
        await page.wait_for_timeout(600)

        el = page.locator(selector)
        bbox = await el.bounding_box()
        if bbox:
            fit_w = max(width, int(bbox["width"] + 60))
            fit_h = int(bbox["height"] + 60)
            await page.set_viewport_size({"width": fit_w, "height": fit_h})
            await page.wait_for_timeout(300)
        await el.screenshot(path=output_path)
        await browser.close()

    size_kb = os.path.getsize(output_path) / 1024
    # Report final dimensions
    from PIL import Image
    with Image.open(output_path) as im:
        w, h = im.size
    print(f"OK {output_path} ({size_kb:.0f}KB, {w}x{h}px)")


if __name__ == "__main__":
    asyncio.run(html_to_image(HTML, OUT))
