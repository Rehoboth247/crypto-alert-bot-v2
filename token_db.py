"""
Token Database Module

SQLite database for persistent storage of seen tokens.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional

# Database file path
DB_FILE = os.path.join(os.path.dirname(__file__), "tokens.db")


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    return sqlite3.connect(DB_FILE)


def init_db() -> None:
    """
    Initialize the database schema.
    Creates the seen_tokens table if it doesn't exist.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT UNIQUE NOT NULL,
            symbol TEXT,
            name TEXT,
            chain TEXT,
            liquidity_usd REAL,
            market_cap REAL,
            alert_price REAL DEFAULT 0,
            milestones_hit TEXT DEFAULT '',
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_token_address 
        ON seen_tokens(token_address)
    """)
    
    # Add new columns if they don't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE seen_tokens ADD COLUMN alert_price REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE seen_tokens ADD COLUMN milestones_hit TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    conn.commit()
    conn.close()
    print(f"[TokenDB] Database initialized at {DB_FILE}")


def is_token_seen(token_address: str) -> bool:
    """
    Check if a token has already been seen/alerted.
    
    Args:
        token_address: Token contract address.
        
    Returns:
        True if token was already alerted, False if new.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT 1 FROM seen_tokens WHERE token_address = ?",
        (token_address.lower(),)
    )
    
    result = cursor.fetchone() is not None
    conn.close()
    
    return result


def mark_token_seen(
    token_address: str,
    symbol: str = "",
    name: str = "",
    chain: str = "",
    liquidity_usd: float = 0,
    market_cap: float = 0,
    alert_price: float = 0
) -> None:
    """
    Mark a token as seen/alerted in the database.
    
    Args:
        token_address: Token contract address.
        symbol: Token symbol.
        name: Token name.
        chain: Blockchain (e.g., "solana").
        liquidity_usd: Liquidity in USD.
        market_cap: Market cap in USD.
        alert_price: Price at time of alert (for tracking).
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO seen_tokens 
            (token_address, symbol, name, chain, liquidity_usd, market_cap, alert_price, milestones_hit)
            VALUES (?, ?, ?, ?, ?, ?, ?, '')
        """, (
            token_address.lower(),
            symbol,
            name,
            chain,
            liquidity_usd,
            market_cap,
            alert_price
        ))
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"[TokenDB] Error saving token: {e}")
    finally:
        conn.close()


def get_seen_count() -> int:
    """
    Get the total number of seen tokens.
    
    Returns:
        Count of tokens in database.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM seen_tokens")
    count = cursor.fetchone()[0]
    
    conn.close()
    return count


def clear_old_tokens(days_to_keep: int = 7) -> int:
    """
    Clear tokens older than the specified number of days.
    
    Args:
        days_to_keep: Number of days of history to retain.
    
    Returns:
        Number of tokens that were cleared.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Calculate cutoff date
    cursor.execute(f"SELECT date('now', '-{days_to_keep} days')")
    cutoff_date = cursor.fetchone()[0]
    
    # Get count to be cleared
    cursor.execute(
        "SELECT COUNT(*) FROM seen_tokens WHERE alerted_at < datetime('now', ?)",
        (f'-{days_to_keep} days',)
    )
    count = cursor.fetchone()[0]
    
    if count > 0:
        # Delete old tokens
        cursor.execute(
            "DELETE FROM seen_tokens WHERE alerted_at < datetime('now', ?)",
            (f'-{days_to_keep} days',)
        )
        conn.commit()
        print(f"[TokenDB] Cleaned up {count} tokens older than {days_to_keep} days")
    else:
        print(f"[TokenDB] Database clean. No tokens older than {days_to_keep} days.")
        
    conn.close()
    return count


def clear_all_tokens() -> int:
    """
    Clear all tokens from the database (manual reset).
    kept for backward compatibility and manual resets.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM seen_tokens")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def get_recent_tokens(limit: int = 10) -> list[dict]:
    """
    Get the most recently seen tokens.
    
    Args:
        limit: Maximum number of tokens to return.
        
    Returns:
        List of token dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT token_address, symbol, name, chain, liquidity_usd, market_cap, alerted_at
        FROM seen_tokens
        ORDER BY alerted_at DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "token_address": row[0],
            "symbol": row[1],
            "name": row[2],
            "chain": row[3],
            "liquidity_usd": row[4],
            "market_cap": row[5],
            "alerted_at": row[6]
        }
        for row in rows
    ]


def get_tokens_for_price_tracking() -> list[dict]:
    """
    Get all tokens with alert prices for price movement tracking.
    
    Returns:
        List of tokens with their alert prices and milestones already hit.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT token_address, symbol, name, chain, alert_price, milestones_hit
        FROM seen_tokens
        WHERE alert_price > 0
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "token_address": row[0],
            "symbol": row[1],
            "name": row[2],
            "chain": row[3],
            "alert_price": row[4],
            "milestones_hit": row[5] or ""
        }
        for row in rows
    ]


def update_milestone_hit(token_address: str, milestone: str) -> None:
    """
    Record that a price milestone was hit for a token.
    
    Args:
        token_address: Token contract address.
        milestone: Milestone identifier (e.g., "2x", "5x", "10x", "-50%").
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get current milestones
    cursor.execute(
        "SELECT milestones_hit FROM seen_tokens WHERE token_address = ?",
        (token_address.lower(),)
    )
    row = cursor.fetchone()
    
    if row:
        current = row[0] or ""
        if milestone not in current:
            new_milestones = f"{current},{milestone}" if current else milestone
            cursor.execute(
                "UPDATE seen_tokens SET milestones_hit = ? WHERE token_address = ?",
                (new_milestones, token_address.lower())
            )
            conn.commit()
    
    conn.close()


# Initialize database on module import
init_db()
