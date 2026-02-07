"""
Dexscreener Scraper Module

Uses Selenium with advanced stealth techniques to scrape Dexscreener.
Implements "Grab Everything, Filter Later" logic for robustness.
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

# Rate limiting - delay between API calls (seconds)
API_DELAY = 1.5


def create_driver():
    """
    Creates a Chrome driver configured to bypass bot detection.
    """
    options = Options()
    
    # 1. Use the new Headless mode (indistinguishable from headful in many cases)
    options.add_argument("--headless=new")
    
    # 2. Standard Linux/Docker flags
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # 3. Critical: Disable automation flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # 4. Use a realistic User-Agent
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    
    # 5. execute_cdp_cmd: The Magic Bullet
    # This prevents the website from checking `navigator.webdriver` via JavaScript
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    
    time.sleep(2) # Give CDP command a moment
    
    return driver


def check_for_blocking(driver) -> bool:
    """
    Checks if the scraper is blocked by WAF/Cloudflare.
    Returns True if blocked.
    """
    try:
        title = driver.title.lower()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Common blocking indicators
        blocking_keywords = [
            "access denied",
            "access to this page has been denied",
            "challenge",
            "verify you are human",
            "cloudflare",
            "just a moment",
            "attention required",
            "security check"
        ]
        
        if any(keyword in title for keyword in blocking_keywords):
            print(f"[Scraper] 🚨 BLOCKED DETECTED via Title: {driver.title}")
            return True
            
        # Check body text for specific blocking messages
        if "unable to access dexscreener.com" in body or "got an error when visiting dexscreener.com" in body:
             print(f"[Scraper] 🚨 BLOCKED DETECTED via Body Text")
             return True
             
        return False
        
    except Exception as e:
        print(f"[Scraper] Error checking for blocking: {e}")
        return False


def scrape_dexscreener_pairs() -> list[dict]:
    """
    Scrape the Dexscreener filtered page using robust link extraction.
    
    Returns:
        List of dicts with chain, pair_address, and partial token info.
    """
    print("[Scraper] Opening Dexscreener (Stealth Mode)...")
    
    driver = None
    try:
        driver = create_driver()
        driver.get(DEXSCREENER_FILTER_URL)
        
        # Check for blocking immediately after load
        if check_for_blocking(driver):
            raise Exception("SCRAPER_BLOCKED")
        
        # Wait for content to load (wait for any link to appear)
        print("[Scraper] Waiting for page load...")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
        except:
            print("[Scraper] Warning: Timeout waiting for page content")
        
        # Scroll to load more tokens
        print("[Scraper] Scrolling...")
        for i in range(5):
            driver.execute_script("window.scrollBy(0, 1500);")
            time.sleep(1)
        
        # Extraction Logic: "Grab Everything, Filter Later"
        # Instead of searching for specific classes, we grab ALL links.
        links = driver.find_elements(By.TAG_NAME, "a")
        print(f"[Scraper] Found {len(links)} total links. Filtering...")
        
        unique_pairs = set()
        pairs = []
        
        for link in links:
            try:
                href = link.get_attribute("href")
                if not href:
                    continue
                
                # Filter for token pair patterns
                # Matches: dexscreener.com/chain-name/address or /chain-name/address
                # Robust regex to handle full URLs or relative paths
                match = re.search(r'dexscreener\.com/([^/]+)/([a-zA-Z0-9]+)$', href)
                if not match:
                     match = re.search(r'/([^/]+)/([a-zA-Z0-9]+)$', href)
                
                if match:
                    chain = match.group(1)
                    pair_address = match.group(2)
                    
                    # 1. Filter out invalid "chains" that are actually domains or subdomains
                    if '.' in chain or chain == 'api':
                        continue

                    # 2. Filter out common navigation paths
                    if chain in ['watchlist', 'new-pairs', 'gainers', 'losers', 'u', 'trends', 'portfolio', 'multicharts', 'product', 'developers', 'about', 'privacy', 'terms']:
                        continue
                        
                    # 3. Filter out if address looks like a navigation keyword (just in case)
                    if pair_address in ['watchlist', 'new-pairs', 'gainers', 'losers', 'u', 'trends', 'portfolio', 'multicharts', 'product']:
                       continue
                    
                    # Create a unique key
                    key = f"{chain}/{pair_address}"
                    
                    if key not in unique_pairs:
                        unique_pairs.add(key)
                        
                        # We don't have symbol/name yet, but we have the ID to fetch it via API
                        pairs.append({
                            "chain": chain,
                            "pair_address": pair_address,
                            "symbol": "???", # Will be filled by API
                            "name": "",      # Will be filled by API
                            "href": href
                        })
            except Exception as e:
                continue
                
        print(f"[Scraper] Extracted {len(pairs)} unique pairs")
        return pairs
        
    except Exception as e:
        print(f"[Scraper] Error: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


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


def get_best_pair_for_token(token_address: str) -> Optional[dict]:
    """
    Fetch the best pair (highest liquidity) for a given token address.
    Uses 'dex/tokens/{tokenAddress}' endpoint.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if not pairs:
            return None
            
        # Sort by liquidity desc just in case
        pairs.sort(key=lambda x: x.get("liquidity", {}).get("usd", 0) or 0, reverse=True)
        return pairs[0]
        
    except Exception as e:
        print(f"[Scraper] Error fetching token best pair {token_address}: {e}")
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
    
    print(f"[Scraper] Processing {len(scraped_pairs)} pairs...")
    
    new_tokens = []
    already_seen = 0
    
    for scraped in scraped_pairs:
        chain_name = scraped["chain"]
        pair_address = scraped["pair_address"]
        
        # Rate limit delay before API call
        time.sleep(API_DELAY)
        
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
        
        # Get Twitter URL
        twitter_url = get_twitter_from_pair(pair_data)
        
        # Log if no Twitter found but still process
        if not twitter_url:
            symbol = base_token.get("symbol", "???")
            # print(f"[Scraper] Note: {symbol} has no Twitter in API")
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
        
        # Limit to processing reasonable amount to avoid long loop times if scraping returned hundreds
        if len(new_tokens) >= 30:
            print("[Scraper] Reached batch limit of 30 new tokens")
            break
    
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
    price_usd = float(pair.get("priceUsd", 0) or 0)
    
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
        "price_usd": price_usd,
        "dexscreener_url": profile.get("url", ""),
        "description": "",
    }


def save_token_to_db(token_info: dict) -> None:
    """Save token to database with alert price for tracking."""
    mark_token_seen(
        token_address=token_info.get("address", ""),
        symbol=token_info.get("symbol", ""),
        name=token_info.get("name", ""),
        chain=token_info.get("chain", ""),
        liquidity_usd=token_info.get("liquidity_usd", 0),
        market_cap=token_info.get("market_cap", 0),
        alert_price=token_info.get("price_usd", 0)
    )

if __name__ == "__main__":
    # Test the independent scraper function
    print("Testing Stealth Scraper...")
    pairs = scrape_dexscreener_pairs()
    print(f"Scraped {len(pairs)} pairs.")
    for p in pairs[:5]:
        print(f" - {p}")
