"""
Crypto Alert Bot V3 - Main Entry Point

Monitors Dexscreener for new tokens every 1 hour (silent discovery),
tracks them for 7 days, and sends alerts on price milestones (+50%, 2x, 5x, 10x).
"""

import asyncio
import concurrent.futures
import os
import signal
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import modules after loading env vars
# Using scraper instead of API for complete data
from dex_scraper import get_new_filtered_tokens, get_token_info, save_token_to_db
from narrative_analyzer import analyze_token_narrative
from telegram_alerter import send_alert, send_startup_message, send_price_movement_alert, send_error_alert
from token_db import get_seen_count, clear_expired_tokens
from price_tracker import check_all_price_movements
from telegram_commands import run_command_listener

# Configuration
POLL_INTERVAL_HOURS = 1  # Poll every 1 hour (24 times per day)
TOKEN_EXPIRY_HOURS = 168  # Track each token for 7 days (168h)

# Thread pool for running blocking I/O (scraper, API calls)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# Graceful shutdown flag
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print("\n[Main] Shutdown signal received. Stopping...")
    shutdown_event.set()


async def process_token(token_data: dict) -> None:
    """
    Process a single token: Silent Discovery.
    Just save to database for tracking. Alerts happen on price performance.
    """
    try:
        token_info = get_token_info(token_data)
        symbol = token_info.get("symbol", "???")
        name = token_info.get("name", "Unknown")
        
        print(f"[Main] 🕵️ Silent Discovery: {name} (${symbol}) - Tracking started")
        
        # Save to database immediately (no initial alert)
        save_token_to_db(token_info)
            
    except Exception as e:
        print(f"[Main] Error processing token: {e}")


async def poll_loop() -> None:
    """
    Main polling loop. Checks for new tokens every hour.
    Tokens tracked for 7 days then auto-removed.
    """
    print(f"[Main] Starting polling loop (interval: {POLL_INTERVAL_HOURS} hours)")
    print(f"[Main] Polling every {POLL_INTERVAL_HOURS} hour(s)")
    print(f"[Main] Token tracking: {TOKEN_EXPIRY_HOURS}h per-token expiry (no midnight reset)")
    print(f"[Main] Price milestones: 2x, 5x, 10x alerts enabled")
    print(f"[Main] Filters: minLiq$60k, minMcap$300k, min24hVol$2M, min24hChg20%, min6hChg5%")
    
    # Send startup notification
    await send_startup_message()
    
    # Initial check
    await run_check()
    
    while not shutdown_event.is_set():
        # Calculate next poll time
        next_poll = get_next_poll_time()
        wait_seconds = (next_poll - datetime.now()).total_seconds()
        
        if wait_seconds > 0:
            print(f"[Main] Next check at: {next_poll.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds/60:.1f} minutes)")
            
            # Wait for next poll time or shutdown
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=wait_seconds
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Time for next check
        
        await run_check()


def get_next_poll_time() -> datetime:
    """
    Calculate the next hourly poll time.
    """
    now = datetime.now()
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


async def run_check() -> None:
    """Run a single check for new tokens and price movements."""
    print(f"\n[Main] {'='*40}")
    print(f"[Main] Checking for new tokens at {datetime.now().strftime('%H:%M:%S')}")
    print(f"[Main] {'='*40}")
    
    try:
        # Clean up expired tokens (24h per-token expiry)
        clear_expired_tokens(hours=TOKEN_EXPIRY_HOURS)
        
        # Run blocking scraper in thread executor to avoid freezing Telegram commands
        loop = asyncio.get_event_loop()
        new_tokens = await loop.run_in_executor(_executor, get_new_filtered_tokens)
        
        if new_tokens:
            print(f"[Main] Found {len(new_tokens)} new token(s) matching criteria")
            
            for token_data in new_tokens:
                await process_token(token_data)
                # Small delay between tokens
                await asyncio.sleep(5)
        else:
            print(f"[Main] No new tokens matching criteria")
        
        # Check price movements on previously alerted tokens
        print(f"\n[Main] Checking price movements on tracked tokens...")
        price_alerts = await check_all_price_movements()
        
        for alert in price_alerts:
            await send_price_movement_alert(alert)
            await asyncio.sleep(1)
        
        # Show database stats
        seen_count = get_seen_count()
        print(f"[Main] Total tokens in database: {seen_count}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"[Main] Error in check: {error_msg}")
        
        # Classify error and send appropriate alert
        if "SCRAPER_BLOCKED" in error_msg:
            await send_error_alert(
                "⚠️ **SCRAPER BLOCKED** ⚠️\n\n"
                "DexScreener WAF/Cloudflare block detected.\n"
                "Scraping is paused for this cycle.\n\n"
                "**Action:** Check logs or wait for IP rotation."
            )
        elif "session not created" in error_msg or "Chrome" in error_msg:
            await send_error_alert(
                "💀 **CHROME CRASHED** 💀\n\n"
                "The Selenium Chrome browser failed to start.\n"
                f"Error: `{error_msg[:200]}`\n\n"
                "**Action:** The bot will retry next cycle.\n"
                "If this keeps happening, a redeploy may be needed."
            )
        else:
            await send_error_alert(
                f"❌ **BOT ERROR** ❌\n\n"
                f"An unexpected error occurred during the check cycle.\n"
                f"Error: `{error_msg[:200]}`\n\n"
                "**Action:** Check Railway logs for details."
            )


async def main() -> None:
    """
    Main entry point for the crypto alert bot.
    """
    print("=" * 50)
    print("🚀 Crypto Alert Bot V2 Starting...")
    print(f"📅 Checking every {POLL_INTERVAL_HOURS} hours")
    print(f"⏱️ Token tracking: {TOKEN_EXPIRY_HOURS}h per token")
    print(f"🎯 Price milestones: 2x, 5x, 10x")
    print("=" * 50)
    
    # Validate required environment variables
    required_vars = [
        ("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN")),
        ("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID")),
        ("GROQ_API_KEY", os.getenv("GROQ_API_KEY")),
    ]
    
    missing_vars = [name for name, value in required_vars if not value]
    
    if missing_vars:
        print("\n⚠️  Warning: Missing environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the command listener and polling loop concurrently
    await asyncio.gather(
        run_command_listener(),
        poll_loop(),
        return_exceptions=True
    )
    
    print("[Main] Bot stopped. Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
