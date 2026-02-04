"""
Price Tracker Module

Monitors price movements of alerted tokens and sends follow-up alerts
when significant milestones are hit (2x, 5x, 10x, -50%).
"""

import requests
from typing import Optional
from token_db import get_tokens_for_price_tracking, update_milestone_hit

# Price movement thresholds
MILESTONES = {
    "2x": 2.0,      # 100% gain
    "5x": 5.0,      # 400% gain
    "10x": 10.0,    # 900% gain
}
DUMP_THRESHOLD = -0.50  # 50% loss


def get_current_price(chain: str, token_address: str) -> Optional[float]:
    """
    Fetch current token price from Dexscreener API.
    
    Args:
        chain: Blockchain (e.g., "solana", "ethereum").
        token_address: Token contract address.
        
    Returns:
        Current price in USD, or None if unavailable.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if pairs:
            # Get price from highest liquidity pair
            best_pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0) or 0)
            price_usd = best_pair.get("priceUsd")
            if price_usd:
                return float(price_usd)
        return None
    except Exception as e:
        return None


def check_price_milestones(token: dict) -> list[dict]:
    """
    Check if a token has hit any price milestones.
    
    Args:
        token: Token dict with token_address, symbol, chain, alert_price, milestones_hit.
        
    Returns:
        List of milestone alerts to send.
    """
    alerts = []
    
    alert_price = token.get("alert_price", 0)
    if alert_price <= 0:
        return alerts
    
    # Get current price
    current_price = get_current_price(token["chain"], token["token_address"])
    if current_price is None:
        return alerts
    
    milestones_hit = token.get("milestones_hit", "")
    price_change = (current_price - alert_price) / alert_price
    multiplier = current_price / alert_price
    
    # Check gain milestones (2x, 5x, 10x)
    for milestone_name, threshold in MILESTONES.items():
        if milestone_name not in milestones_hit and multiplier >= threshold:
            alerts.append({
                "type": "gain",
                "milestone": milestone_name,
                "token": token,
                "alert_price": alert_price,
                "current_price": current_price,
                "multiplier": multiplier,
                "change_percent": price_change * 100
            })
            # Record milestone as hit
            update_milestone_hit(token["token_address"], milestone_name)
    
    # Check dump threshold (-50%)
    if "-50%" not in milestones_hit and price_change <= DUMP_THRESHOLD:
        alerts.append({
            "type": "dump",
            "milestone": "-50%",
            "token": token,
            "alert_price": alert_price,
            "current_price": current_price,
            "multiplier": multiplier,
            "change_percent": price_change * 100
        })
        update_milestone_hit(token["token_address"], "-50%")
    
    return alerts


async def check_all_price_movements() -> list[dict]:
    """
    Check all tracked tokens for price movements.
    
    Returns:
        List of all milestone alerts.
    """
    tokens = get_tokens_for_price_tracking()
    
    if not tokens:
        print("[PriceTracker] No tokens to track")
        return []
    
    print(f"[PriceTracker] Checking {len(tokens)} tokens for price movements...")
    
    all_alerts = []
    for token in tokens:
        try:
            alerts = check_price_milestones(token)
            all_alerts.extend(alerts)
        except Exception as e:
            print(f"[PriceTracker] Error checking {token.get('symbol', '???')}: {e}")
    
    if all_alerts:
        print(f"[PriceTracker] Found {len(all_alerts)} milestone alert(s)")
    else:
        print("[PriceTracker] No new milestones hit")
    
    return all_alerts
