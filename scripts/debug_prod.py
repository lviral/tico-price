"""Diagnóstico: abre ticoprice.app, captura errores de consola y de red."""
import asyncio
from collections import Counter
from playwright.async_api import async_playwright

errors = Counter()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on("console", lambda m: m.type == "error" and errors.update([m.text[:120]]))
        page.on("requestfailed", lambda r: print(f"[reqfail] {r.url[:120]} -> {r.failure}"))
        await page.goto("https://ticoprice.app/", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.locator("button:has-text('Aires')").first.click()
        await page.wait_for_timeout(5000)
        info = await page.evaluate(
            """() => {
            const imgs = [...document.querySelectorAll('img.card-img')];
            return {
              cardLike: [...new Set([...document.querySelectorAll('[class*="card"]')].map(e => e.className))].slice(0, 12),
              imgCount: imgs.length,
              imgsBroken: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
              imgsOk: imgs.filter(i => i.naturalWidth > 0).length,
              firstImgSrc: imgs[0] ? imgs[0].src : null,
              firstCardHTML: (document.querySelector('[class*="card"]') || {}).outerHTML?.slice(0, 800) || null,
            };
            }"""
        )
        for k, v in info.items():
            print(f"{k}: {v}")
        print("--- errores de consola (agrupados) ---")
        for msg, n in errors.most_common(5):
            print(f"x{n}: {msg}")
        await page.screenshot(path="scripts/prod_screenshot.png")
        await browser.close()


asyncio.run(main())
