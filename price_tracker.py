"""
Price Tracker Module

Monitors price movements including batched updates to respect rate limits.
"""

import asyncio
import requests
from typing import Optional, Dict, List
from token_db import get_tokens_for_price_tracking, update_milestone_hit
from narrative_analyzer import analyze_token_narrative
from dex_scraper import get_pair_details, get_token_info

# Price movement thresholds
MILESTONES = {
    "+50%": 1.5,    # 50% gain
    "2x": 2.0,      # 100% gain
    "5x": 5.0,      # 400% gain
    "10x": 10.0,    # 900% gain
}

# Dexscreener limits
BATCH_SIZE = 30
BATCH_DELAY = 1.5  # Seconds between batches

def get_current_prices_batch(addresses: List[str]) -> Dict[str, float]:
    """
    Fetch current prices for a batch of tokens.
    
    Args:
        addresses: List of token addresses (max 30).
        
    Returns:
        Dictionary mapping address -> price_usd.
    """
    if not addresses:
        return {}
        
    try:
        # Join addresses with comma
        addr_str = ",".join(addresses)
        url = f"https://api.dexscreener.com/latest/dex/tokens/{addr_str}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        prices = {}
        pairs = data.get("pairs", [])
        
        # Group pairs by base token address
        token_best_pairs = {}
        
        for pair in pairs:
            base_token = pair.get("baseToken", {})
            address = base_token.get("address", "").lower()
            if not address:
                continue
                
            liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
            
            # Keep track of best pair for this address
            if address not in token_best_pairs or liquidity > token_best_pairs[address]["liq"]:
                token_best_pairs[address] = {
                    "liq": liquidity,
                    "price": float(pair.get("priceUsd", 0) or 0)
                }
        
        # Extract final prices
        for address, data in token_best_pairs.items():
            if data["price"] > 0:
                prices[address] = data["price"]
                
        return prices
        
    except Exception as e:
        print(f"[PriceTracker] Batch error: {e}")
        return {}


async def check_price_milestones(token: dict, current_price: float) -> list[dict]:
    """
    Check if a token has hit any price milestones using known current price.
    """
    alerts = []
    
    alert_price = token.get("alert_price", 0)
    if alert_price <= 0 or current_price <= 0:
        return alerts
    
    milestones_hit = token.get("milestones_hit", "")
    price_change = (current_price - alert_price) / alert_price
    multiplier = current_price / alert_price
    
    # Check gain milestones
    for milestone_name, threshold in MILESTONES.items():
        if milestone_name not in milestones_hit and multiplier >= threshold:
            print(f"[PriceTracker] 🚀 Milestone {milestone_name} hit for {token.get('symbol')}!")
            
            # Enrich with full token data for the alert
            chain = token.get("chain", "solana")
            address = token.get("token_address", "")
            
            # Fetch fresh details
            pair_data = get_pair_details(chain, address)
            if pair_data:
                # Mock enrich structure for get_token_info
                enriched = {
                    "pair": pair_data,
                    "profile": {
                        "chainId": chain,
                        "tokenAddress": address,
                        "url": pair_data.get("url", ""),
                        "links": pair_data.get("info", {}).get("socials", []) or []
                    }
                }
                full_info = get_token_info(enriched)
            else:
                full_info = token # Fallback
            
            # Run AI Analysis
            analysis = await analyze_token_narrative(full_info)
            
            alerts.append({
                "type": "gain",
                "milestone": milestone_name,
                "token": full_info,
                "analysis": analysis,
                "alert_price": alert_price,
                "current_price": current_price,
                "multiplier": multiplier,
                "change_percent": price_change * 100
            })
            update_milestone_hit(token["token_address"], milestone_name)
    
    return alerts


async def check_all_price_movements() -> list[dict]:
    """
    Check all tracked tokens for price movements using batched requests.
    """
    tokens = get_tokens_for_price_tracking()
    
    if not tokens:
        print("[PriceTracker] No tokens to track")
        return []
    
    print(f"[PriceTracker] Checking {len(tokens)} tokens (Batch size: {BATCH_SIZE})")
    
    all_alerts = []
    
    # Process in batches
    for i in range(0, len(tokens), BATCH_SIZE):
        batch = tokens[i:i + BATCH_SIZE]
        addresses = [t["token_address"] for t in batch]
        
        prices = get_current_prices_batch(addresses)
        
        # Process each token in batch
        for token in batch:
            address = token["token_address"].lower()
            current_price = prices.get(address)
            
            if current_price:
                # check_price_milestones is now async
                alerts = await check_price_milestones(token, current_price)
                all_alerts.extend(alerts)
        
        # Rate limit delay between batches
        if i + BATCH_SIZE < len(tokens):
            await asyncio.sleep(BATCH_DELAY)
    
    if all_alerts:
        print(f"[PriceTracker] Found {len(all_alerts)} milestone alert(s)")
    else:
        print("[PriceTracker] No new milestones hit")
    
    return all_alerts
