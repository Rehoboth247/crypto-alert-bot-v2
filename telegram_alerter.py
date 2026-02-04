"""
Telegram Alerter Module

Sends formatted token alerts to a Telegram channel.
"""

import os
from telegram import Bot
from telegram.error import TelegramError

# Load environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def format_number(value: float) -> str:
    """
    Format a number for display (e.g., 5000 -> $5.0K).
    
    Args:
        value: Numeric value to format.
        
    Returns:
        Formatted string.
    """
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    else:
        return f"${value:.0f}"


def format_alert_message(token_info: dict, analysis: dict) -> str:
    """
    Format the alert message as plain text.
    """
    name = token_info.get("name", "Unknown")
    symbol = token_info.get("symbol", "???")
    chain = token_info.get("chain", "Unknown")
    liquidity = token_info.get("liquidity_usd", 0)
    market_cap = token_info.get("market_cap", 0)
    volume_24h = token_info.get("volume_24h", 0)
    price_change = token_info.get("price_change_24h", 0)
    price_change_6h = token_info.get("price_change_6h", 0)
    dex_url = token_info.get("dexscreener_url", "")
    twitter_url = token_info.get("twitter_url", "")
    
    narrative = analysis.get("narrative", "Unknown")
    verdict = analysis.get("verdict", "Unknown")
    summary = analysis.get("summary", "No summary available.")
    
    # Format numbers
    liq_str = format_number(liquidity)
    mcap_str = format_number(market_cap)
    vol_str = format_number(volume_24h)
    
    message = f"""🚨 New Token Alert: {name} (${symbol})
⛓️ Chain: {chain.upper()}

💰 Liquidity: {liq_str}
📊 Market Cap: {mcap_str}
📈 24h Volume: {vol_str}
{'🟢' if price_change >= 0 else '🔴'} 24h Change: {price_change:+.1f}%
{'🟢' if price_change_6h >= 0 else '🔴'} 6h Change: {price_change_6h:+.1f}%

📖 Narrative: {narrative}
🧠 Verdict: {verdict}

📝 {summary}

🔗 Dexscreener: {dex_url}
"""
    
    if twitter_url:
        message += f"🐦 Twitter: {twitter_url}\n"
    
    return message


async def send_alert(token_info: dict, analysis: dict) -> bool:
    """
    Send a token alert to the configured Telegram channel.
    
    Args:
        token_info: Dictionary with token details.
        analysis: Dictionary with narrative analysis.
        
    Returns:
        True if message sent successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[TelegramAlerter] Error: TELEGRAM_BOT_TOKEN not set")
        return False
    
    if not TELEGRAM_CHAT_ID:
        print("[TelegramAlerter] Error: TELEGRAM_CHAT_ID not set")
        return False
    
    # Format the message
    message = format_alert_message(token_info, analysis)
    
    try:
        # Create bot instance
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Send message (no parse_mode to avoid markdown issues)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            disable_web_page_preview=False
        )
        
        print(f"[TelegramAlerter] Alert sent for {token_info.get('symbol', 'Unknown')}")
        return True
        
    except TelegramError as e:
        print(f"[TelegramAlerter] Telegram API error: {e}")
        return False
    except Exception as e:
        print(f"[TelegramAlerter] Unexpected error: {e}")
        return False


async def send_startup_message() -> bool:
    """
    Send a startup notification to confirm the bot is running.
    
    Returns:
        True if message sent successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="🤖 Crypto Alert Bot Started\n\nMonitoring Dexscreener for new tokens..."
        )
        
        return True
        
    except Exception as e:
        print(f"[TelegramAlerter] Failed to send startup message: {e}")
        return False
