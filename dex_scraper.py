"""
Dexscreener Scraper Module

Uses Selenium to scrape the actual Dexscreener filtered page.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from typing import Optional
import requests
from token_db import is_token_seen, mark_token_seen

# The Dexscreener filter URL
DEXSCREENER_FILTER_URL = (
    "https://dexscreener.com/new-pairs?"
    "rankBy=pairAge&order=asc"
    "&minLiq=60000"
    "&minMarketCap=300000"
    "&maxFdv=10000000000"
    "&min24HBuys=2"
    "&min24HSells=2"
    "&min24HVol=2000000"
    "&min24HChg=20"
    "&min6HChg=5"
    "&profile=1"
)


def create_driver():
    """Create a headless Chrome driver (works in Docker)."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=options)
    return driver


def scrape_dexscreener_pairs() -> list[dict]:
    """
    Scrape the Dexscreener filtered page for pair data.
    
    Returns:
        List of dicts with chain, pair_address, and token info.
    """
    print("[Scraper] Opening Dexscreener...")
    
    try:
        driver = create_driver()
        driver.get(DEXSCREENER_FILTER_URL)
        
        # Wait for table to load
        print("[Scraper] Waiting for page load...")
        time.sleep(5)
        
        # Try to wait for rows
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ds-dex-table-row"))
            )
        except:
            print("[Scraper] Warning: Could not find table rows")
        
        # Scroll to load more tokens
        for i in range(6):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(0.8)
        
        # Scroll back to top and down again to ensure all loaded
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        for i in range(6):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(0.5)
        
        # Extract pair data from rows
        pairs = []
        rows = driver.find_elements(By.CSS_SELECTOR, ".ds-dex-table-row")
        
        print(f"[Scraper] Found {len(rows)} rows")
        
        for row in rows:
            try:
                href = row.get_attribute("href")
                if not href:
                    continue
                
                # Parse href: /solana/pairAddress
                match = re.match(r'/([^/]+)/([^/?]+)', href.replace("https://dexscreener.com", ""))
                if not match:
                    continue
                
                chain = match.group(1)
                pair_address = match.group(2)
                
                # Get symbol and name
                try:
                    symbol_el = row.find_element(By.CSS_SELECTOR, ".ds-dex-table-row-base-token-symbol")
                    symbol = symbol_el.text
                except:
                    symbol = "???"
                
                try:
                    name_el = row.find_element(By.CSS_SELECTOR, ".ds-dex-table-row-base-token-name")
                    name = name_el.text
                except:
                    name = ""
                
                pairs.append({
                    "chain": chain,
                    "pair_address": pair_address,
                    "symbol": symbol,
                    "name": name,
                    "href": href
                })
                
            except Exception as e:
                continue
        
        driver.quit()
        print(f"[Scraper] Extracted {len(pairs)} pairs")
        return pairs
        
    except Exception as e:
        print(f"[Scraper] Error: {e}")
        try:
            driver.quit()
        except:
            pass
        return []


def get_pair_details(chain: str, pair_address: str) -> Optional[dict]:
    """
    Fetch detailed pair data from Dexscreener API.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if pairs:
            return pairs[0]
        return None
    except Exception as e:
        print(f"[Scraper] Error fetching pair {pair_address}: {e}")
        return None


def get_token_profile(chain: str, token_address: str) -> Optional[dict]:
    """Check if token has a Dexscreener profile and get Twitter link."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if pairs:
            pair = pairs[0]
            info = pair.get("info", {})
            return {
                "socials": info.get("socials", []),
                "websites": info.get("websites", []),
                "imageUrl": info.get("imageUrl", "")
            }
        return None
    except:
        return None


def get_twitter_from_pair(pair_data: dict) -> Optional[str]:
    """Extract Twitter URL from pair info."""
    info = pair_data.get("info", {})
    socials = info.get("socials", [])
    
    for social in socials:
        if social.get("type") == "twitter":
            return social.get("url", "")
    return None


def get_new_filtered_tokens(chain: str = None) -> list[dict]:
    """
    Scrape Dexscreener and return new tokens matching criteria.
    """
    # Scrape the page
    scraped_pairs = scrape_dexscreener_pairs()
    
    # Filter to Solana only if specified
    if chain:
        scraped_pairs = [p for p in scraped_pairs if p["chain"].lower() == chain.lower()]
    else:
        # Default to all chains shown
        pass
    
    print(f"[Scraper] Processing {len(scraped_pairs)} pairs...")
    
    new_tokens = []
    already_seen = 0
    
    for scraped in scraped_pairs:
        chain_name = scraped["chain"]
        pair_address = scraped["pair_address"]
        
        # Get full pair details
        pair_data = get_pair_details(chain_name, pair_address)
        if not pair_data:
            continue
        
        # Get token address
        base_token = pair_data.get("baseToken", {})
        token_address = base_token.get("address", "")
        
        if not token_address:
            continue
        
        # Check if already seen
        if is_token_seen(token_address):
            already_seen += 1
            continue
        
        # Get Twitter URL if available (profile=1 in URL already filters, so be lenient)
        twitter_url = get_twitter_from_pair(pair_data)
        
        # Log if no Twitter found but still process
        if not twitter_url:
            symbol = base_token.get("symbol", "???")
            print(f"[Scraper] Note: {symbol} has no Twitter in API, using profile page link")
            # Try to get any social link
            info = pair_data.get("info", {})
            socials = info.get("socials", [])
            if socials:
                twitter_url = socials[0].get("url", "")
        
        # Build enriched data
        enriched = {
            "profile": {
                "chainId": chain_name,
                "tokenAddress": token_address,
                "url": f"https://dexscreener.com/{chain_name}/{pair_address}",
                "links": [{"type": "twitter", "url": twitter_url}]
            },
            "pair": pair_data
        }
        
        new_tokens.append(enriched)
        
        # Log
        symbol = base_token.get("symbol", "???")
        liq = pair_data.get("liquidity", {}).get("usd", 0) or 0
        vol = pair_data.get("volume", {}).get("h24", 0) or 0
        chg = pair_data.get("priceChange", {}).get("h24", 0) or 0
        print(f"[Scraper] ✓ {symbol}: Liq=${liq:,.0f}, Vol=${vol:,.0f}, 24h={chg:+.0f}%")
    
    print(f"[Scraper] Found {len(new_tokens)} new tokens, {already_seen} already seen")
    return new_tokens


def get_token_info(enriched_data: dict) -> dict:
    """Extract token information for display."""
    profile = enriched_data.get("profile", {})
    pair = enriched_data.get("pair", {})
    
    chain_id = profile.get("chainId", "")
    token_address = profile.get("tokenAddress", "")
    
    base_token = pair.get("baseToken", {})
    symbol = base_token.get("symbol", "???")
    name = base_token.get("name", "Unknown")
    
    liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
    market_cap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0
    volume_24h = pair.get("volume", {}).get("h24", 0) or 0
    price_change_24h = pair.get("priceChange", {}).get("h24", 0) or 0
    price_change_6h = pair.get("priceChange", {}).get("h6", 0) or 0
    
    # Get Twitter
    twitter_url = None
    links = profile.get("links", [])
    for link in links:
        if link.get("type") == "twitter":
            twitter_url = link.get("url")
            break
    
    return {
        "name": name,
        "symbol": symbol,
        "chain": chain_id,
        "address": token_address,
        "twitter_url": twitter_url,
        "liquidity_usd": liquidity,
        "market_cap": market_cap,
        "volume_24h": volume_24h,
        "price_change_24h": price_change_24h,
        "price_change_6h": price_change_6h,
        "dexscreener_url": profile.get("url", ""),
        "description": "",
    }


def save_token_to_db(token_info: dict) -> None:
    """Save token to database."""
    mark_token_seen(
        token_address=token_info.get("address", ""),
        symbol=token_info.get("symbol", ""),
        name=token_info.get("name", ""),
        chain=token_info.get("chain", ""),
        liquidity_usd=token_info.get("liquidity_usd", 0),
        market_cap=token_info.get("market_cap", 0)
    )
