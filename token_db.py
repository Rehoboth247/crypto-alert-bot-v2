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
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_token_address 
        ON seen_tokens(token_address)
    """)
    
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
    market_cap: float = 0
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
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO seen_tokens 
            (token_address, symbol, name, chain, liquidity_usd, market_cap)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            token_address.lower(),
            symbol,
            name,
            chain,
            liquidity_usd,
            market_cap
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


def clear_all_tokens() -> int:
    """
    Clear all tokens from the database (daily reset).
    
    Returns:
        Number of tokens that were cleared.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get count before clearing
    cursor.execute("SELECT COUNT(*) FROM seen_tokens")
    count = cursor.fetchone()[0]
    
    # Clear all tokens
    cursor.execute("DELETE FROM seen_tokens")
    conn.commit()
    conn.close()
    
    print(f"[TokenDB] Cleared {count} tokens from database (daily reset)")
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


# Initialize database on module import
init_db()
