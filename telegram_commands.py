"""
Telegram Commands Module

Handles bot commands like /status to query the token database.
"""

import os
import asyncio
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def format_number(value: float) -> str:
    """Format a number for display."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    else:
        return f"${value:.0f}"


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - show database stats and recent tokens."""
    from token_db import get_seen_count, get_recent_tokens
    
    try:
        count = get_seen_count()
        recent = get_recent_tokens(limit=15)
        
        now = datetime.now()
        
        message = f"""📊 **Crypto Alert Bot Status**
🕐 Time: {now.strftime('%Y-%m-%d %H:%M:%S')} WAT

📈 **Tokens Seen Today:** {count}

"""
        
        if recent:
            message += "🔥 **Recent Tokens:**\n"
            for i, token in enumerate(recent[:15], 1):
                symbol = token.get('symbol', '???')
                name = token.get('name', 'Unknown')
                liq = format_number(token.get('liquidity_usd', 0))
                mcap = format_number(token.get('market_cap', 0))
                chain = token.get('chain', '').upper()
                
                message += f"{i}. **{symbol}** ({name})\n"
                message += f"   💰 {liq} | 📊 {mcap} | ⛓️ {chain}\n"
        else:
            message += "📭 No tokens stored yet today.\n"
        
        message += "\n💡 Database resets at midnight WAT."
        
        await update.message.reply_text(message)
        print(f"[Commands] /status sent to {update.effective_user.username}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        print(f"[Commands] Error in /status: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    message = """🤖 **Crypto Alert Bot Commands**

/status - View stored tokens today
/help - Show this help message

📊 The bot monitors Dexscreener every 6 hours
🔄 Database resets daily at midnight WAT
"""
    await update.message.reply_text(message)


async def run_command_listener():
    """Run the Telegram command listener in the background."""
    if not TELEGRAM_BOT_TOKEN:
        print("[Commands] Warning: TELEGRAM_BOT_TOKEN not set, commands disabled")
        return
    
    try:
        # Create application
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("help", help_command))
        
        # Start polling for commands
        print("[Commands] Starting command listener...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        
        # Keep running until stopped
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"[Commands] Error in command listener: {e}")
