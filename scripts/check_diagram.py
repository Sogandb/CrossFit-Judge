#!/usr/bin/env python3
"""Verify diagram rendering: fonts, overflow, clipping checks."""
import asyncio
from playwright.async_api import async_playwright

HTML = "/home/z/my-project/scripts/architecture_diagram.html"


async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1320, "height": 900})
        await page.goto(f"file://{HTML}", wait_until="networkidle")
        await page.wait_for_timeout(600)

        result = await page.evaluate(
            """() => {
        const out = {};
        // 1. Which font is actually applied to body text?
        const step = document.querySelector('.phase-step');
        out.appliedFont = getComputedStyle(step).fontFamily;
        // measure real glyph rendering via canvas
        const c = document.createElement('canvas');
        const ctx = c.getContext('2d');
        ctx.font = '16px Vazirmatn';
        const w_vazir = ctx.measureText('\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627').width;
        ctx.font = '16px monospace';
        const w_mono = ctx.measureText('\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627').width;
        ctx.font = '16px "DejaVu Sans"';
        const w_dejavu = ctx.measureText('\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627').width;
        out.fontWidths = { vazir: w_vazir, mono: w_mono, dejavu: w_dejavu };

        // 2. Overflow check: any .phase-step text overflowing its box?
        let overflows = [];
        document.querySelectorAll('.phase-step, .phase-title, .loopback').forEach((el, i) => {
          if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) {
            overflows.push({idx: i, cls: el.className, sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight, text: el.textContent.slice(0, 30)});
          }
        });
        out.overflows = overflows;

        // 3. Root bounding box
        const root = document.getElementById('root');
        const rb = root.getBoundingClientRect();
        out.rootBox = { w: rb.width, h: rb.height };

        // 4. Count tofu (missing glyph) - check a sample of Persian chars render with non-zero width in Vazirmatn
        // If Vazirmatn loaded, appliedFont contains it and widths differ from fallback
        return out;
      }"""
        )
        print(result)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(check())
