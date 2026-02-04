"""
Dexscreener Monitoring Module

Fetches and filters tokens from Dexscreener with local filtering.
Uses multiple API endpoints to find tokens matching criteria.
"""

import requests
from typing import Optional
from token_db import is_token_seen, mark_token_seen

# API endpoints
DEX_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_BOOSTED_URL = "https://api.dexscreener.com/token-boosts/latest/v1"

# Filter configuration (matching user's Dexscreener URL)
FILTER_CONFIG = {
    "chain": None,  # All chains
    "min_liquidity_usd": 60_000,
    "min_market_cap": 300_000,
    "max_market_cap": 10_000_000_000,
    "min_24h_buys": 2,
    "min_24h_sells": 2,
    "min_24h_volume": 2_000_000,
    "min_24h_change_pct": 20,
    "min_6h_change_pct": 5,
    "require_profile": True,
}


def fetch_token_profiles() -> list[dict]:
    """Fetch the latest token profiles from Dexscreener."""
    try:
        response = requests.get(DEX_PROFILES_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[DexMonitor] Error fetching profiles: {e}")
        return []


def fetch_boosted_tokens() -> list[dict]:
    """Fetch boosted tokens from Dexscreener."""
    try:
        response = requests.get(DEX_BOOSTED_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[DexMonitor] Error fetching boosted: {e}")
        return []


def get_twitter_link(data: dict) -> Optional[str]:
    """Extract Twitter/X link from token's links array."""
    links = data.get("links", [])
    for link in links:
        link_type = link.get("type", "").lower()
        url = link.get("url", "")
        if link_type == "twitter" or "twitter.com" in url or "x.com" in url:
            return url
    return None


def get_pair_data(token_address: str) -> Optional[dict]:
    """Fetch detailed pair data for a token."""
    try:
        pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(pair_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if pairs:
            # Return the pair with highest liquidity on Solana
            solana_pairs = [p for p in pairs if p.get("chainId", "").lower() == "solana"]
            if solana_pairs:
                return max(solana_pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0) or 0)
            return max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0) or 0)
        return None
    except Exception as e:
        print(f"[DexMonitor] Error fetching pair: {e}")
        return None


def filter_pair(pair_data: dict, config: dict = FILTER_CONFIG) -> bool:
    """
    Apply all filter criteria to a pair.
    
    Returns True if pair passes ALL filters.
    """
    if not pair_data:
        return False
    
    # Check chain (if specified)
    if config.get("chain"):
        chain_id = pair_data.get("chainId", "").lower()
        if chain_id != config["chain"].lower():
            return False
    
    # Check liquidity (must be >= $60,000)
    liquidity = pair_data.get("liquidity", {}).get("usd", 0) or 0
    if liquidity < config["min_liquidity_usd"]:
        return False
    
    # Check market cap ($300k - $10B)
    market_cap = pair_data.get("marketCap", 0) or pair_data.get("fdv", 0) or 0
    if market_cap < config["min_market_cap"]:
        return False
    if market_cap > config["max_market_cap"]:
        return False
    
    # Check 24h buys (>= 2)
    txns = pair_data.get("txns", {})
    h24 = txns.get("h24", {})
    buys_24h = h24.get("buys", 0) or 0
    if buys_24h < config.get("min_24h_buys", 0):
        return False
    
    # Check 24h sells (>= 2)
    sells_24h = h24.get("sells", 0) or 0
    if sells_24h < config["min_24h_sells"]:
        return False
    
    # Check 24h volume (>= $2,000,000)
    volume_24h = pair_data.get("volume", {}).get("h24", 0) or 0
    if volume_24h < config["min_24h_volume"]:
        return False
    
    # Check 24h price change (>= 20%)
    price_change = pair_data.get("priceChange", {})
    change_24h = price_change.get("h24", 0) or 0
    if change_24h < config["min_24h_change_pct"]:
        return False
    
    # Check 6h price change (>= 5%)
    change_6h = price_change.get("h6", 0) or 0
    if change_6h < config["min_6h_change_pct"]:
        return False
    
    return True


def get_new_filtered_tokens(chain: str = None) -> list[dict]:
    """
    Fetch tokens and filter by criteria.
    
    Combines data from multiple sources:
    1. Token profiles (tokens with Dexscreener profiles)
    2. Boosted tokens
    
    Returns list of enriched token data that passes all filters.
    """
    config = FILTER_CONFIG.copy()
    if chain:
        config["chain"] = chain
    
    target_chain = config["chain"].lower()
    
    # Collect unique token addresses from all sources
    token_addresses = {}  # address -> profile data
    
    # Source 1: Token profiles (have Dexscreener profile = profile=1)
    profiles = fetch_token_profiles()
    for profile in profiles:
        if profile.get("chainId", "").lower() == target_chain:
            addr = profile.get("tokenAddress", "")
            if addr:
                token_addresses[addr.lower()] = profile
    
    # Source 2: Boosted tokens
    boosted = fetch_boosted_tokens()
    for token in boosted:
        if token.get("chainId", "").lower() == target_chain:
            addr = token.get("tokenAddress", "")
            if addr and addr.lower() not in token_addresses:
                token_addresses[addr.lower()] = token
    
    print(f"[DexMonitor] Found {len(token_addresses)} Solana tokens with profiles")
    
    # Filter and collect results
    new_tokens = []
    checked = 0
    passed = 0
    already_seen = 0
    
    for addr, profile in token_addresses.items():
        # Check if already alerted
        if is_token_seen(addr):
            already_seen += 1
            continue
        
        checked += 1
        
        # Get detailed pair data
        pair_data = get_pair_data(addr)
        if not pair_data:
            continue
        
        # Apply filters
        if not filter_pair(pair_data, config):
            continue
        
        # Check for Twitter link
        if not get_twitter_link(profile):
            continue
        
        passed += 1
        
        # Enrich data
        enriched = {
            "profile": profile,
            "pair": pair_data
        }
        new_tokens.append(enriched)
        
        # Log each passing token
        base_token = pair_data.get("baseToken", {})
        symbol = base_token.get("symbol", "???")
        liq = pair_data.get("liquidity", {}).get("usd", 0) or 0
        vol = pair_data.get("volume", {}).get("h24", 0) or 0
        chg = pair_data.get("priceChange", {}).get("h24", 0) or 0
        print(f"[DexMonitor] ✓ {symbol}: Liq=${liq:,.0f}, Vol=${vol:,.0f}, 24h={chg:+.0f}%")
    
    print(f"[DexMonitor] Checked {checked} new tokens, {passed} passed filters, {already_seen} already seen")
    return new_tokens


def get_token_info(enriched_data: dict) -> dict:
    """Extract relevant token information for display."""
    profile = enriched_data.get("profile", {})
    pair = enriched_data.get("pair", {})
    
    chain_id = profile.get("chainId", pair.get("chainId", ""))
    token_address = profile.get("tokenAddress", "")
    
    # Get symbol and name from pair data
    base_token = pair.get("baseToken", {})
    symbol = base_token.get("symbol", "???")
    name = base_token.get("name", profile.get("description", "Unknown"))
    
    # Get metrics
    liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
    market_cap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0
    volume_24h = pair.get("volume", {}).get("h24", 0) or 0
    price_change_24h = pair.get("priceChange", {}).get("h24", 0) or 0
    price_change_6h = pair.get("priceChange", {}).get("h6", 0) or 0
    
    return {
        "name": name,
        "symbol": symbol,
        "chain": chain_id,
        "address": token_address,
        "twitter_url": get_twitter_link(profile),
        "liquidity_usd": liquidity,
        "market_cap": market_cap,
        "volume_24h": volume_24h,
        "price_change_24h": price_change_24h,
        "price_change_6h": price_change_6h,
        "dexscreener_url": profile.get("url", f"https://dexscreener.com/{chain_id}/{token_address}"),
        "icon": profile.get("icon", ""),
        "description": profile.get("description", ""),
    }


def save_token_to_db(token_info: dict) -> None:
    """Save a token to the database after alerting."""
    mark_token_seen(
        token_address=token_info.get("address", ""),
        symbol=token_info.get("symbol", ""),
        name=token_info.get("name", ""),
        chain=token_info.get("chain", ""),
        liquidity_usd=token_info.get("liquidity_usd", 0),
        market_cap=token_info.get("market_cap", 0)
    )
