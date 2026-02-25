import time
import requests
from enum import Enum
from smart_money_config import BIRDEYE_API_KEY, BIRDEYE_BASE_URL, REQUEST_DELAY_SECONDS


class Chain(Enum):
    SOLANA = "solana"
    BASE = "base"
    ETHEREUM = "ethereum"
    BSC = "bsc"
    TRON = "tron"
    MONAD = "monad"
    ARBITRUM = "arbitrum"
    AVALANCHE = "avalanche"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    ZKSYNC = "zksync"
    SUI = "sui"
    MEGAETH = "megaeth"
    HYPERLIQUID = "hyperliquid"


class BirdeyeClient:
    """Rate-limited Birdeye API client for the Standard tier (1 RPS, 30K CUs/mo)."""

    def __init__(self, api_key: str = BIRDEYE_API_KEY):
        if not api_key:
            raise ValueError("BIRDEYE_API_KEY is not set. Add it to your .env file.")
        self.api_key = api_key
        self.base_url = BIRDEYE_BASE_URL
        self._last_request_time = 0.0

    # ── Internal helpers ──────────────────────────────────────────

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)

    def _get(self, endpoint: str, chain: Chain, params: dict = None):
        """Make a GET request with rate limiting, retries on 429."""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "X-API-KEY": self.api_key,
            "x-chain": chain.value,
            "accept": "application/json",
        }

        self._rate_limit()
        self._last_request_time = time.time()

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)

            # Always try to parse JSON body first for better error messages
            try:
                body = resp.json()
            except ValueError:
                body = {}

            if resp.status_code == 429 or (
                resp.status_code == 400
                and "too many" in str(body.get("message", "")).lower()
            ):
                print("  ⚠ Rate limit hit — backing off 5s...")
                time.sleep(5)
                return self._get(endpoint, chain, params)

            if resp.status_code == 401:
                print("  ✖ Auth error: invalid or expired API key.")
                return None

            if resp.status_code >= 400:
                msg = body.get("message", resp.text[:120])
                print(f"  ✖ HTTP {resp.status_code}: {msg}")
                return None

            if body.get("success") is False:
                print(f"  ✖ API error: {body.get('message', 'unknown')}")
                return None

            return body.get("data")

        except requests.exceptions.RequestException as exc:
            print(f"  ✖ Request failed: {exc}")
            return None

    # ── Public endpoints (Standard tier) ──────────────────────────

    def get_token_holders(self, token_address: str, chain: Chain,
                          limit: int = 100, offset: int = 0):
        """
        GET /defi/v3/token/holder
        Returns the top holders for a specific token by balance.
        Max limit per call: 100.
        """
        capped_limit = min(limit, 100)
        return self._get("/defi/v3/token/holder", chain, params={
            "address": token_address,
            "offset": offset,
            "limit": capped_limit,
        })

    def get_token_holders_paginated(self, token_address: str, chain: Chain,
                                    total: int = 100):
        """Fetch multiple pages of top holders (100 per page) up to `total`."""
        all_holders = []
        fetched = 0
        while fetched < total:
            data = self.get_token_holders(
                token_address, chain, limit=min(100, total - fetched),
                offset=fetched,
            )
            if not data or "items" not in data or not data["items"]:
                break
            all_holders.extend(data["items"])
            fetched += len(data["items"])
            if len(data["items"]) < 100:
                break  # No more pages
        return all_holders

