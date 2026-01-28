import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

import asyncpg
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define Timezones
UTC = timezone.utc

# Configuration
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", 5))
DATABASE_CONNSTR = os.getenv("DATABASE_CONNSTR")

# Global database connection pool
db_pool = None


async def init_database():
    """Initialize PostgreSQL tables."""
    global db_pool
    if not DATABASE_CONNSTR:
        logger.error("DATABASE_CONNSTR not set")
        return

    db_pool = await asyncpg.create_pool(DATABASE_CONNSTR)
    
    async with db_pool.acquire() as conn:
        # Create rates table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rates (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL,
                source_name VARCHAR NOT NULL,
                rate DOUBLE PRECISION NOT NULL
            )
        """)

        # Create indices
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rates_timestamp ON rates(timestamp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_rates_source ON rates(source_name)")

    logger.info("Database initialized successfully")


async def save_rate(source_name: str, rate: float, timestamp: datetime = None):
    """Save a rate to the database."""
    try:
        # Use UTC timezone for storage
        if timestamp is None:
            timestamp = datetime.now(UTC)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = timestamp.astimezone(UTC)

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rates (timestamp, source_name, rate)
                VALUES ($1, $2, $3)
                """,
                timestamp, source_name, rate
            )
        logger.info(f"Saved rate for {source_name}: {rate}")
    except Exception as e:
        logger.error(f"Failed to save rate for {source_name}: {e}")


async def scrape_google_n_revolut_rate():
    """Scrape SGD to MYR rate from Google Finance and Revolut."""
    stealth = Stealth()
    # headless_mode = os.getenv("HEADLESS_SCRAPE", "True").lower() == "true"
    headless_mode = False
    # page_1_rate = None
    page_2_rate = None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless_mode, 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        await stealth.apply_stealth_async(context)
        # page_1 = await context.new_page()
        page_2 = await context.new_page()

        # # Scrape Google Finance
        # url = "https://www.google.com/finance/quote/SGD-MYR"
        # logger.info(f"Navigating to {url}...")
        # try:
        #     await page_1.goto(url)
        #     await page_1.wait_for_selector('div[data-last-price]', timeout=5000)
        #     rate = await page_1.locator('div[data-last-price]').get_attribute('data-last-price')
        #     page_1_rate = float(rate)
        # except Exception as e:
        #     logger.error(f"Failed to scrape Google rate: {e}")
        
        # Scrape Revolut
        url = "https://www.revolut.com/currency-converter/convert-sgd-to-myr-exchange-rate/"
        logger.info(f"Navigating to {url}...")
        try:
            await page_2.goto(url)
            if await page_2.locator('span', has_text="Reject non-essential cookies").first.count() > 0:
                await page_2.locator('span', has_text="Reject non-essential cookies").first.click()
            await page_2.locator('foreignObject span', has_text="RM").wait_for(state="visible", timeout=5000)
            text = await page_2.locator('foreignObject span', has_text="RM").text_content()
            text = text.replace('\xa0', ' ')
            match = re.search(r'RM\s*([\d.]+)', text)
            if match:
                page_2_rate = float(match.group(1))
        except Exception as e:
            logger.error(f"Failed to scrape Revolut rate: {e}")
        
        await browser.close()
    
    return [page_2_rate]


async def scrape_and_save():
    """Scrape rates and save to database."""
    logger.info("Starting rate scraping...")
    
    now_utc = datetime.now(UTC)
    
    try:
        rates = await scrape_google_n_revolut_rate()
        
        # # Save Google rate
        # if rates[0] is not None:
        #     await save_rate("Google", rates[0], timestamp=now_utc)
        # else:
        #     logger.warning("No rate obtained from Google")
        
        # Save Revolut rate
        if rates[0] is not None:
            await save_rate("Revolut", rates[1], timestamp=now_utc)
        else:
            logger.warning("No rate obtained from Revolut")
            
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
    
    logger.info("Scraping complete.")


async def main():
    """Main entry point."""
    # Initialize database
    await init_database()
    
    # Setup scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scrape_and_save,
        "interval",
        minutes=SCRAPE_INTERVAL,
        id="scrape_rates",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started. Scraping every {SCRAPE_INTERVAL} minutes.")
    
    # Run initial scrape
    await scrape_and_save()
    
    # Keep the script running
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.shutdown()
        if db_pool:
            await db_pool.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
