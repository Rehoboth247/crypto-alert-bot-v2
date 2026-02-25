import requests
import time
from typing import Dict, Any
from smart_money_config import MORALIS_API_KEY
from birdeye_client import Chain

class MoralisClient:
    """Client for Moralis to fetch EVM token holders."""
    BASE_URL = "https://deep-index.moralis.io/api/v2.2"

    def __init__(self):
        self.api_key = MORALIS_API_KEY
        self.headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key
        }

    def _map_chain(self, chain: Chain) -> str:
        """Map our internal Chain enum to Moralis chain identifiers."""
        mapping = {
            Chain.ETHEREUM: "eth",
            Chain.BSC: "bsc",
            Chain.BASE: "base",
            Chain.ARBITRUM: "arbitrum",
            Chain.AVALANCHE: "avalanche",
            Chain.OPTIMISM: "optimism",
            Chain.POLYGON: "polygon"
        }
        return mapping.get(chain, chain.value)

    def get_token_holders_paginated(self, token_address: str, chain: Chain, total: int = 100) -> list:
        """Fetch multiple pages of top holders (up to `total`) from Moralis.
        Returns a list of dictionaries mirroring the Birdeye ui_amount structure."""
        if not self.api_key:
            return []

        all_holders = []
        moralis_chain = self._map_chain(chain)
        url = f"{self.BASE_URL}/erc20/{token_address}/owners"
        
        # Start pagination
        params = {"chain": moralis_chain, "limit": min(total, 100)}
        cursor = None

        while len(all_holders) < total:
            if cursor:
                params["cursor"] = cursor

            try:
                res = requests.get(url, headers=self.headers, params=params, timeout=10)
                res.raise_for_status()
                data = res.json()
            except requests.exceptions.HTTPError as e:
                return []
            except requests.exceptions.RequestException:
                time.sleep(2) # Backoff on connection error
                continue

            results = data.get("result", [])
            if not results:
                break
            
            # Translate Moralis output structure to match what Analyzer expects from Birdeye
            for holder in results:
                all_holders.append({
                    "owner": holder.get("owner_address", ""),
                    "ui_amount": float(holder.get("balance_formatted", 0))
                })

            if len(all_holders) >= total:
                break

            cursor = data.get("cursor")
            if not cursor:
                break  # No more pages
                
        # API doesn't guarantee strict sorting by balance for every network
        # Fallback sorting just in case
        all_holders.sort(key=lambda x: x["ui_amount"], reverse=True)
        return all_holders[:total]
