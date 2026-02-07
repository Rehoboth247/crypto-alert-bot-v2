"""
GMGN Scraper Module

Scrapes GMGN.ai to detect "Smart Money" activity and "Smart Followers".
Uses the same Selenium driver as dex_scraper.py.
"""

import time
import re
from typing import Optional, Dict
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dex_scraper import create_driver

# GMGN URL Template
GMGN_TOKEN_URL = "https://gmgn.ai/sol/token/{}"

def check_gmgn_smart_money(token_address: str) -> Dict:
    """
    Check GMGN.ai for Smart Money activity and followers.
    
    Args:
        token_address: The token's contract address.
        
    Returns:
        Dict with keys:
        - smart_buy_count: Number of buys by smart wallets
        - smart_sell_count: Number of sells by smart wallets
        - smart_buy_vol: Total volume of smart buys (USD)
        - smart_followers: Count of "Renowned/Smart" followers
    """
    url = GMGN_TOKEN_URL.format(token_address)
    print(f"[GMGN] Checking {url}...")
    
    result = {
        "smart_buy_count": 0,
        "smart_sell_count": 0,
        "smart_buy_vol": 0.0,
        "smart_followers": 0
    }
    
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        
        # Wait for page load
        time.sleep(5)
        
        # 1. Get Smart/Renowned Followers (from header)
        try:
            # Use JS to find the Renowned/Smart followers count robustly
            # We look for the specific "Renowned" or "Smart" text in the header area
            followers_count = driver.execute_script("""
                // Strategy: Find elements containing 'Renowned' or 'Smart' in their text/title
                // and extract the number associated with them.
                
                function findFollowersCount() {
                    // 1. Try identifying by text content in the header bar
                    const header = document.querySelector('.flex.items-center.pl-16px');
                    if (header) {
                        const text = header.innerText;
                        // Look for patterns like "9 Renowned" or similar if they exist
                        // based on observation, checking child nodes is better
                    }

                    // 2. Search for tooltip/title attributes (highly reliable for icons)
                    const icons = Array.from(document.querySelectorAll('[title*="Renowned"], [title*="Smart"], [aria-label*="Renowned"], [aria-label*="Smart"]'));
                    for (const icon of icons) {
                        // The number is usually in the parent's text or a sibling
                        const container = icon.closest('div'); 
                        if (container) {
                            const text = container.innerText;
                            const match = text.match(/(\\d+)/);
                            if (match) return parseInt(match[0]);
                        }
                    }

                    // 3. Text search in the top area (fallback)
                    // The "Renowned Followers" count is often just a number next to an icon.
                    // Let's look for the specific text "Renowned" or "Smart" if visible.
                    
                    const candidates = Array.from(document.querySelectorAll('div, span, p'));
                    for (const el of candidates) {
                        if (el.innerText === 'Renowned' || el.innerText === 'Smart' || el.innerText.includes('Renowned Followers')) {
                             // Look for number nearby
                             const parent = el.parentElement;
                             if (parent) {
                                 const match = parent.innerText.match(/(\\d+)/);
                                 if (match) return parseInt(match[0]);
                             }
                        }
                    }

                    return 0;
                }
                
                return findFollowersCount();
            """)
            
            # If 0, try a more direct approach for the "9" we saw
            if not followers_count:
                # Based on the screenshot, it's a number next to a person icon.
                # Let's try to get numbers from the header and make a best guess if needed,
                # or just accept 0 if we can't be sure (to avoid false positives).
                pass
            
            result['smart_followers'] = int(followers_count) if followers_count else 0
            if result['smart_followers'] > 0:
                print(f"[GMGN] Found {result['smart_followers']} Smart/Renowned followers")
            
        except Exception as e:
            print(f"[GMGN] Error getting followers: {e}")

        # 2. Check Smart Money Trades
        try:
            # Click "Trades" or "Activity" tab
            try:
                # Use JS click for reliability
                driver.execute_script("""
                    const tab = document.getElementById('rc-tabs-0-tab-activity');
                    if (tab) tab.click();
                    else {
                        // Try finding by text
                        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
                        const t = tabs.find(x => x.textContent.includes('Activity') || x.textContent.includes('Trades'));
                        if (t) t.click();
                    }
                """)
            except:
                print("[GMGN] Could not click Trades tab")
            
            time.sleep(3)
            
            # Scan table rows for "Smart" badge
            # We use a JS script to parse the table content efficiently
            trades_data = driver.execute_script("""
                const uniqueTrades = [];
                const rows = Array.from(document.querySelectorAll('.g-table-body .ds-dex-table-row, .g-table-body > div'));
                
                rows.forEach(row => {
                    const html = row.innerHTML;
                    
                    // Identify Smart Money by the specific badge image
                    const isSmart = html.includes('gmgn_sm.png') || html.includes('Smart Money') || html.includes('smart_money');
                    
                    if (isSmart) {
                        const text = row.textContent;
                        
                        // Determine Buy vs Sell
                        // "Buy" is usually green, "Sell" red. Text contains "Buy"/"Sell"
                        const isBuy = text.includes('Buy');
                        const isSell = text.includes('Sell');
                        
                        if (!isBuy && !isSell) return; // Skip if unclear
                        
                        // Extract Amount
                        // Strategy: Look for the column with "$". 
                        // The text often looks like: "Buy  0.5 SOL  $1,234.56"
                        // pass regex to find $ value
                        
                        let amount = 0;
                        const match = text.match(/\\$([0-9,.]+)/);
                        if (match) {
                            amount = parseFloat(match[1].replace(/,/g, ''));
                        }
                        
                        uniqueTrades.push({
                            is_buy: isBuy,
                            is_sell: isSell,
                            amount: amount || 0
                        });
                    }
                });
                return uniqueTrades;
            """)
            
            for trade in trades_data:
                if trade['is_buy']:
                    result['smart_buy_count'] += 1
                    result['smart_buy_vol'] += trade['amount']
                elif trade['is_sell']:
                    result['smart_sell_count'] += 1
            
            if result['smart_buy_count'] > 0 or result['smart_sell_count'] > 0:
                print(f"[GMGN] Found {result['smart_buy_count']} smart buys (${result['smart_buy_vol']:.0f}), {result['smart_sell_count']} smart sells")
            else:
                print("[GMGN] No smart money trades found in recent history")
                    
        except Exception as e:
            print(f"[GMGN] Error checking trades: {e}")
            
    except Exception as e:
        print(f"[GMGN] Scraper error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return result

if __name__ == "__main__":
    import sys
    # Allow running with a token address argument
    token = "2DfBjrPFZjDTiCY6pxchS6aSdUdEpkm7PdqpovHjBAGS"
    if len(sys.argv) > 1:
        token = sys.argv[1]
        
    print(f"Testing GMGN scraper for {token}...")
    data = check_gmgn_smart_money(token)
    print(f"Result: {data}")
