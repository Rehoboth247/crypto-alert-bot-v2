"""
Crypto Alert Bot - Main Entry Point

Monitors Dexscreener for new tokens every 2 hours,
analyzes their narrative, and sends alerts to Telegram.
Each token is tracked for 24 hours then auto-removed (no midnight reset).
"""

import asyncio
import os
import signal
from datetime import datetime, timedelta, time as dt_time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import modules after loading env vars
# Using scraper instead of API for complete data
from dex_scraper import get_new_filtered_tokens, get_token_info, save_token_to_db
from narrative_analyzer import analyze_token_narrative
from telegram_alerter import send_alert, send_startup_message, send_price_movement_alert
from token_db import get_seen_count, clear_expired_tokens
from price_tracker import check_all_price_movements
from telegram_commands import run_command_listener

# Configuration
POLL_INTERVAL_HOURS = 1  # Poll every 1 hour (24 times per day)
TOKEN_EXPIRY_HOURS = 168  # Track each token for 7 days (168h)

# Poll times in UTC (every hour)
# Since we poll every hour, we just need a list of 0-23
POLL_TIMES = list(range(24))

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
    Main polling loop that checks for new tokens every 2 hours.
    Polls at fixed times: 00:00, 02:00, 04:00, ... 22:00 WAT
    Each token tracked for 24 hours then auto-removed (no midnight reset).
    """
    print(f"[Main] Starting polling loop (interval: {POLL_INTERVAL_HOURS} hours)")
    print(f"[Main] Fixed poll times (UTC): {POLL_TIMES}")
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
    Calculate the next scheduled poll time.
    Returns the next time from POLL_TIMES that's in the future.
    """
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    
    # Build list of all upcoming poll times (today and tomorrow)
    upcoming_times = []
    
    for hour in POLL_TIMES:
        # Today's poll time
        poll_time_today = datetime.combine(today, dt_time(hour=hour, minute=0, second=0))
        if poll_time_today > now:
            upcoming_times.append(poll_time_today)
        
        # Tomorrow's poll time (for wrap-around)
        poll_time_tomorrow = datetime.combine(tomorrow, dt_time(hour=hour, minute=0, second=0))
        upcoming_times.append(poll_time_tomorrow)
    
    # Sort and return the earliest future time
    upcoming_times.sort()
    return upcoming_times[0] if upcoming_times else datetime.combine(tomorrow, dt_time(hour=POLL_TIMES[0], minute=0, second=0))


async def run_check() -> None:
    """Run a single check for new tokens and price movements."""
    print(f"\n[Main] {'='*40}")
    print(f"[Main] Checking for new tokens at {datetime.now().strftime('%H:%M:%S')}")
    print(f"[Main] {'='*40}")
    
    try:
        # Clean up expired tokens (24h per-token expiry)
        clear_expired_tokens(hours=TOKEN_EXPIRY_HOURS)
        
        # Check for new tokens
        new_tokens = get_new_filtered_tokens()
        
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
        print(f"[Main] Error in check: {e}")


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
