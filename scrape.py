import os
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncpg
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

async def scrape_google_n_revolut_rate():
    stealth = Stealth()
    headless_mode = os.getenv("HEADLESS_SCRAPE", "True").lower() == "true"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless_mode, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
            )
        await stealth.apply_stealth_async(context)
        page_1 = await context.new_page()

        url = "https://www.revolut.com/currency-converter/convert-sgd-to-myr-exchange-rate/"
        print(f"Navigating to {url}...")
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        try:
            await page_1.goto(url) #, wait_until="networkidle")
            if await page_1.locator('span', has_text="Reject non-essential cookies").first.count() > 0:
                await page_1.locator('span', has_text="Reject non-essential cookies").first.click()
            # await page_1.locator('button[role="tab"]', has_text="1d").click()
            await page_1.locator('foreignObject span', has_text="RM").wait_for(state="visible", timeout=5000)
            text = await page_1.locator('foreignObject span', has_text="RM").text_content()
            text = text.replace('\xa0', ' ')
            match = re.search(r'RM\s*([\d.]+)', text)
            if match:
                page_1_rate = float(match.group(1))
        except Exception as e:
            # await page_1.screenshot(path="revolut_error.png", timeout=5000)
            inner_html = await page_1.evaluate("document.documentElement.innerHTML")
            with open("revolut_error.html", "w", encoding="utf-8") as f:
                f.write(inner_html)
            print(f"Failed to scrape Revolut rate: {e}")
            await context.tracing.stop(path="trace.zip")
        
        await browser.close()
        return page_1_rate

result = await scrape_google_n_revolut_rate()
print(result)