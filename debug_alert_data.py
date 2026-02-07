
import requests
import json
from dex_scraper import get_token_info

# PENGU on Solana (Token Address)
TOKEN_ADDRESS = "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv" 
CHAIN = "solana"

def test_endpoints():
    print(f"Testing for Token Address: {TOKEN_ADDRESS}")
    
    # 1. Test Pairs Endpoint (Current Implementation)
    print("\n--- 1. Testing dex/pairs endpoint (Expect Failure if using Token Addr) ---")
    url_pairs = f"https://api.dexscreener.com/latest/dex/pairs/{CHAIN}/{TOKEN_ADDRESS}"
    try:
        resp = requests.get(url_pairs, timeout=10)
        data = resp.json()
        print(f"URL: {url_pairs}")
        if data.get("pairs"):
            print("✅ Found pairs (Unexpected if this is just a token addr)")
        else:
            print("❌ No pairs found (Expected behavior for token addr)")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Test Tokens Endpoint (Correct Implementation)
    print("\n--- 2. Testing dex/tokens endpoint ---")
    url_tokens = f"https://api.dexscreener.com/latest/dex/tokens/{TOKEN_ADDRESS}"
    try:
        resp = requests.get(url_tokens, timeout=10)
        data = resp.json()
        print(f"URL: {url_tokens}")
        pairs = data.get("pairs", [])
        if pairs:
            print(f"✅ Found {len(pairs)} pairs!")
            best_pair = pairs[0]
            print(f"Top Pair Liq: ${best_pair.get('liquidity', {}).get('usd', 0)}")
            
            # Simulate enrichment using this data
            enriched = {
                "pair": best_pair,
                "profile": {
                    "chainId": CHAIN,
                    "tokenAddress": TOKEN_ADDRESS,
                    "url": best_pair.get("url", ""),
                    "links": best_pair.get("info", {}).get("socials", []) or []
                }
            }
            full_info = get_token_info(enriched)
            print("\nExtracted Info Check:")
            print(f"URL: {full_info.get('dexscreener_url')}")
            print(f"Liq: ${full_info.get('liquidity_usd')}")
            print(f"MC: ${full_info.get('market_cap')}")
            
        else:
            print("❌ No pairs found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoints()
