import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


async def take_screenshots():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # Screenshot 1: React Frontend - Upload Page
        print("Taking React frontend screenshots...")
        await page.goto("http://localhost:5173", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=SCREENSHOT_DIR / "react-upload.png", full_page=True)
        print("  react-upload.png")

        # Screenshot 2: React Frontend - Vault Page (navigate)
        await page.click("text=Vault")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=SCREENSHOT_DIR / "react-vault.png", full_page=True)
        print("  react-vault.png")

        # Screenshot 3: React Frontend - Dashboard Page
        await page.click("text=Dashboard")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=SCREENSHOT_DIR / "react-dashboard.png", full_page=True)
        print("  react-dashboard.png")

        # Screenshot 4: API Docs
        print("Taking API docs screenshot...")
        await page.goto("http://localhost:8000/docs", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=SCREENSHOT_DIR / "api-docs.png", full_page=True)
        print("  api-docs.png")

        await browser.close()
        print(f"\nAll screenshots saved to {SCREENSHOT_DIR}/")


if __name__ == "__main__":
    asyncio.run(take_screenshots())