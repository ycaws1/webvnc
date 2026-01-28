import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import deque

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

import asyncpg
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn
import threading

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

# Track scraping stats
scrape_stats = {
    "total_scrapes": 0,
    "successful_scrapes": 0,
    "failed_scrapes": 0,
    "last_scrape_time": None,
    "last_rate": None,
    "next_scrape_time": None
}

# Store recent logs in memory (max 100 entries)
log_entries = deque(maxlen=100)

# Custom logging handler to capture logs
class LogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_entries.append(log_entry)

# Add custom handler to logger
log_handler = LogHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(log_handler)

# Initialize FastAPI
app = FastAPI(title="SGD to MYR Rate Scraper")


@app.get("/", response_class=HTMLResponse)
async def status_page():
    """Main status page with statistics and logs."""
    
    # Get recent logs
    recent_logs = "\n".join(log_entries)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Scraper Status</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #555;
                margin-top: 0;
            }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }}
            .stat-item {{
                background-color: #f9f9f9;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #4CAF50;
            }}
            .stat-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }}
            .stat-value {{
                font-size: 24px;
                font-weight: bold;
                color: #333;
                margin-top: 5px;
            }}
            .logs {{
                background-color: #1e1e1e;
                color: #d4d4d4;
                padding: 15px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                overflow-x: auto;
                max-height: 500px;
                overflow-y: auto;
            }}
            .logs pre {{
                margin: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .success {{ color: #4CAF50; }}
            .error {{ color: #f44336; }}
            .refresh-notice {{
                text-align: center;
                color: #666;
                font-size: 12px;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <h1>🤖 SGD to MYR Rate Scraper</h1>
        
        <div class="container">
            <h2>📊 Statistics</h2>
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-label">Total Scrapes</div>
                    <div class="stat-value">{scrape_stats['total_scrapes']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Successful</div>
                    <div class="stat-value success">{scrape_stats['successful_scrapes']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Failed</div>
                    <div class="stat-value error">{scrape_stats['failed_scrapes']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Last Rate (Revolut)</div>
                    <div class="stat-value">{scrape_stats['last_rate'] if scrape_stats['last_rate'] else 'N/A'}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Last Scrape</div>
                    <div class="stat-value" style="font-size: 14px;">
                        {scrape_stats['last_scrape_time'].strftime('%Y-%m-%d %H:%M:%S UTC') if scrape_stats['last_scrape_time'] else 'N/A'}
                    </div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Next Scrape</div>
                    <div class="stat-value" style="font-size: 14px;">
                        {scrape_stats['next_scrape_time'].strftime('%Y-%m-%d %H:%M:%S UTC') if scrape_stats['next_scrape_time'] else 'N/A'}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="container">
            <h2>📝 Recent Logs</h2>
            <div class="logs">
                <pre>{recent_logs if recent_logs else 'No logs yet...'}</pre>
            </div>
            <div class="refresh-notice">Page auto-refreshes every 30 seconds</div>
        </div>
    </body>
    </html>
    """
    
    return html


@app.get("/api/stats")
async def get_stats():
    """API endpoint to get statistics as JSON."""
    return {
        "total_scrapes": scrape_stats['total_scrapes'],
        "successful_scrapes": scrape_stats['successful_scrapes'],
        "failed_scrapes": scrape_stats['failed_scrapes'],
        "last_rate": scrape_stats['last_rate'],
        "last_scrape_time": scrape_stats['last_scrape_time'].isoformat() if scrape_stats['last_scrape_time'] else None,
        "next_scrape_time": scrape_stats['next_scrape_time'].isoformat() if scrape_stats['next_scrape_time'] else None,
        "scrape_interval_minutes": SCRAPE_INTERVAL
    }


@app.get("/api/logs")
async def get_logs():
    """API endpoint to get recent logs as JSON."""
    return {
        "logs": list(log_entries),
        "count": len(log_entries)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}


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
    headless_mode = os.getenv("HEADLESS_SCRAPE", "True").lower() == "true"
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
        page_2 = await context.new_page()
        
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
    
    scrape_stats["total_scrapes"] += 1
    now_utc = datetime.now(UTC)
    scrape_stats["last_scrape_time"] = now_utc
    scrape_stats["next_scrape_time"] = now_utc + timedelta(minutes=SCRAPE_INTERVAL)
    
    try:
        rates = await scrape_google_n_revolut_rate()
        
        # Save Revolut rate
        if rates[0] is not None:
            await save_rate("Revolut", rates[0], timestamp=now_utc)
            scrape_stats["last_rate"] = rates[0]
            scrape_stats["successful_scrapes"] += 1
        else:
            logger.warning("No rate obtained from Revolut")
            scrape_stats["failed_scrapes"] += 1
            
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        scrape_stats["failed_scrapes"] += 1
    
    logger.info("Scraping complete.")


def run_fastapi():
    """Run FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


async def main():
    """Main entry point."""
    # Start FastAPI in a background thread
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    logger.info("FastAPI server started on port 8000")
    
    # Give FastAPI time to start
    await asyncio.sleep(2)
    
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
    
    
# import os
# import re
# import asyncio
# import logging
# from datetime import datetime, timedelta, timezone

# from playwright.async_api import async_playwright
# from playwright_stealth import Stealth

# import asyncpg
# from dotenv import load_dotenv
# from apscheduler.schedulers.asyncio import AsyncIOScheduler

# load_dotenv()

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
# logger = logging.getLogger(__name__)

# # Define Timezones
# UTC = timezone.utc

# # Configuration
# SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", 5))
# DATABASE_CONNSTR = os.getenv("DATABASE_CONNSTR")

# # Global database connection pool
# db_pool = None


# async def init_database():
#     """Initialize PostgreSQL tables."""
#     global db_pool
#     if not DATABASE_CONNSTR:
#         logger.error("DATABASE_CONNSTR not set")
#         return

#     db_pool = await asyncpg.create_pool(DATABASE_CONNSTR)
    
#     async with db_pool.acquire() as conn:
#         # Create rates table
#         await conn.execute("""
#             CREATE TABLE IF NOT EXISTS rates (
#                 id SERIAL PRIMARY KEY,
#                 timestamp TIMESTAMPTZ NOT NULL,
#                 source_name VARCHAR NOT NULL,
#                 rate DOUBLE PRECISION NOT NULL
#             )
#         """)

#         # Create indices
#         await conn.execute("CREATE INDEX IF NOT EXISTS idx_rates_timestamp ON rates(timestamp)")
#         await conn.execute("CREATE INDEX IF NOT EXISTS idx_rates_source ON rates(source_name)")

#     logger.info("Database initialized successfully")


# async def save_rate(source_name: str, rate: float, timestamp: datetime = None):
#     """Save a rate to the database."""
#     try:
#         # Use UTC timezone for storage
#         if timestamp is None:
#             timestamp = datetime.now(UTC)
#         elif timestamp.tzinfo is None:
#             timestamp = timestamp.replace(tzinfo=UTC)
#         else:
#             timestamp = timestamp.astimezone(UTC)

#         async with db_pool.acquire() as conn:
#             await conn.execute(
#                 """
#                 INSERT INTO rates (timestamp, source_name, rate)
#                 VALUES ($1, $2, $3)
#                 """,
#                 timestamp, source_name, rate
#             )
#         logger.info(f"Saved rate for {source_name}: {rate}")
#     except Exception as e:
#         logger.error(f"Failed to save rate for {source_name}: {e}")


# async def scrape_google_n_revolut_rate():
#     """Scrape SGD to MYR rate from Google Finance and Revolut."""
#     stealth = Stealth()
#     # headless_mode = os.getenv("HEADLESS_SCRAPE", "True").lower() == "true"
#     headless_mode = False
#     # page_1_rate = None
#     page_2_rate = None
    
#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=headless_mode, 
#             args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
#         )
#         context = await browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#             viewport={'width': 1920, 'height': 1080}
#         )
#         await stealth.apply_stealth_async(context)
#         # page_1 = await context.new_page()
#         page_2 = await context.new_page()

#         # # Scrape Google Finance
#         # url = "https://www.google.com/finance/quote/SGD-MYR"
#         # logger.info(f"Navigating to {url}...")
#         # try:
#         #     await page_1.goto(url)
#         #     await page_1.wait_for_selector('div[data-last-price]', timeout=5000)
#         #     rate = await page_1.locator('div[data-last-price]').get_attribute('data-last-price')
#         #     page_1_rate = float(rate)
#         # except Exception as e:
#         #     logger.error(f"Failed to scrape Google rate: {e}")
        
#         # Scrape Revolut
#         url = "https://www.revolut.com/currency-converter/convert-sgd-to-myr-exchange-rate/"
#         logger.info(f"Navigating to {url}...")
#         try:
#             await page_2.goto(url)
#             if await page_2.locator('span', has_text="Reject non-essential cookies").first.count() > 0:
#                 await page_2.locator('span', has_text="Reject non-essential cookies").first.click()
#             await page_2.locator('foreignObject span', has_text="RM").wait_for(state="visible", timeout=5000)
#             text = await page_2.locator('foreignObject span', has_text="RM").text_content()
#             text = text.replace('\xa0', ' ')
#             match = re.search(r'RM\s*([\d.]+)', text)
#             if match:
#                 page_2_rate = float(match.group(1))
#         except Exception as e:
#             logger.error(f"Failed to scrape Revolut rate: {e}")
        
#         await browser.close()
    
#     return [page_2_rate]


# async def scrape_and_save():
#     """Scrape rates and save to database."""
#     logger.info("Starting rate scraping...")
    
#     now_utc = datetime.now(UTC)
    
#     try:
#         rates = await scrape_google_n_revolut_rate()
        
#         # # Save Google rate
#         # if rates[0] is not None:
#         #     await save_rate("Google", rates[0], timestamp=now_utc)
#         # else:
#         #     logger.warning("No rate obtained from Google")
        
#         # Save Revolut rate
#         if rates[0] is not None:
#             await save_rate("Revolut", rates[0], timestamp=now_utc)
#         else:
#             logger.warning("No rate obtained from Revolut")
            
#     except Exception as e:
#         logger.error(f"Scraping failed: {e}")
    
#     logger.info("Scraping complete.")


# async def main():
#     """Main entry point."""
#     # Initialize database
#     await init_database()
    
#     # Setup scheduler
#     scheduler = AsyncIOScheduler()
#     scheduler.add_job(
#         scrape_and_save,
#         "interval",
#         minutes=SCRAPE_INTERVAL,
#         id="scrape_rates",
#         replace_existing=True
#     )
#     scheduler.start()
#     logger.info(f"Scheduler started. Scraping every {SCRAPE_INTERVAL} minutes.")
    
#     # Run initial scrape
#     await scrape_and_save()
    
#     # Keep the script running
#     try:
#         while True:
#             await asyncio.sleep(60)
#     except KeyboardInterrupt:
#         logger.info("Shutting down...")
#         scheduler.shutdown()
#         if db_pool:
#             await db_pool.close()
#         logger.info("Shutdown complete.")


# if __name__ == "__main__":
#     asyncio.run(main())
