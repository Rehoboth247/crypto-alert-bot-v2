import sys
from typing import Dict, List, Set
from colorama import init, Fore, Style
from smart_money_config import (
    SMART_WALLETS_SOLANA_FILE, SMART_WALLETS_EVM_FILE, DEFAULT_TRADER_LIMIT,
)
from birdeye_client import BirdeyeClient, Chain
from moralis_client import MoralisClient

init(autoreset=True)

C = Fore.CYAN
G = Fore.GREEN
Y = Fore.YELLOW
R = Fore.RED
M = Fore.MAGENTA
W = Fore.WHITE
DIM = Style.DIM
RST = Style.RESET_ALL


class SmartMoneyAnalyzer:
    def __init__(self):
        self.api = BirdeyeClient()
        self.moralis = MoralisClient()

    # ── Main entry point ──────────────────────────────────────────

    def analyze_token(self, token_address: str, chain: Chain,
                      limit: int = DEFAULT_TRADER_LIMIT):
        self._banner(token_address, chain, limit)

        # Phase 1: Build a "known smart money" set from the global leaderboard
        smart_set = self._build_smart_money_set(chain)

        # Phase 2: Fetch this token's top holders and cross-reference
        holders = self._fetch_token_holders(token_address, chain, limit)
        if holders is None:
            return

        # Phase 3: Evaluate each holder
        results = self._evaluate_holders(holders, smart_set)

        # Phase 4: Print the report
        self._print_report(token_address, chain, results, len(holders))

    def count_smart_wallets_in_token(self, token_address: str, chain: Chain, limit: int = 100) -> int:
        """
        Silently scan a token for known smart wallets without printing ASCII reports.
        Returns the integer count of smart wallets found. Ideal for bot integrations.
        """
        smart_set = self._build_smart_money_set(chain, silent=True)
        if not smart_set:
            return 0
            
        holders = self._fetch_token_holders_silent(token_address, chain, limit)
        if holders is None:
            return 0
            
        results = self._evaluate_holders_silent(holders, smart_set)
        return len(results)

    # ── Phase 1: Global smart money set ───────────────────────────

    def _build_smart_money_set(self, chain: Chain, silent: bool = False) -> set:
        """Load the hardcoded smart wallet address list from JSON depending on the chain."""
        if not silent:
            print(f"\n{Y}[1/3] Loading known smart wallets from local file for {chain.value.upper()}...{RST}")
        
        filepath = SMART_WALLETS_SOLANA_FILE if chain == Chain.SOLANA else SMART_WALLETS_EVM_FILE
        
        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Use lowercase for EVM addresses to ensure case-insensitive matching
            if chain == Chain.SOLANA:
                smart_wallets = {item.get("address", "") for item in data if item.get("address")}
            else:
                smart_wallets = {item.get("address", "").lower() for item in data if item.get("address")}
                
            if not silent:
                print(f"  {G}✓ Loaded {len(smart_wallets)} smart wallets.{RST}")
            return smart_wallets
        except Exception as e:
            if not silent:
                print(f"  {R}❌ Failed to load smart wallets: {e}{RST}")
            return set()

    # ── Phase 2: Token top holders ────────────────────────────────

    def _fetch_token_holders(self, token_address: str, chain: Chain,
                             limit: int) -> list | None:
                             
        pages_needed = (limit + 99) // 100  # ceil division
        print(f"\n{Y}[2/3] Fetching top {limit} holders for this token "
              f"({pages_needed} page{'s' if pages_needed > 1 else ''})...{RST}")
              
        if chain == Chain.SOLANA:
            holders = self.api.get_token_holders_paginated(
                token_address, chain, total=limit
            )
        else:
            holders = self.moralis.get_token_holders_paginated(
                token_address, chain, total=limit
            )

        if not holders:
            print(f"{R}❌ Failed to retrieve top holders.{RST}")
            print(f"{DIM}   • Double-check the token address is correct for {chain.value}.{RST}")
            print(f"{DIM}   • Verify the token has recent active holding data.{RST}")
            if chain != Chain.SOLANA and not self.moralis.api_key:
                 print(f"{DIM}   • Missing MORALIS_API_KEY in .env file!{RST}")
            return None

        print(f"  {G}✓ Found {len(holders)} holders to evaluate.{RST}")
        return holders

    # ── Phase 3: Evaluation ───────────────────────────────────────

    def _evaluate_holders(self, holders: list,
                          smart_set: Set[str]) -> List[Dict]:
        print(f"\n{Y}[3/3] Evaluating wallets...{RST}\n")
        results = []

        for i, holder in enumerate(holders, 1):
            addr = holder.get("owner", "???")
            ui_amount = holder.get("ui_amount", 0)

            short = f"{addr[:6]}…{addr[-4:]}"
            prefix = f"  [{i:>3}/{len(holders)}] {short}"

            is_smart = False
            reasons = []

            # Check 1: Is this wallet in our established database?
            # EVM addresses loaded into smart_set are lowercase, so we compare lowercase.
            # Solana addresses are case-sensitive and remain exact.
            if addr in smart_set or addr.lower() in smart_set:
                is_smart = True
                reasons.append(f"🏆 Known Smart Wallet")

            # Note: Removing the 'whale volume' and 'trade count' heuristic checks 
            # since we now strictly define "Smart Money" by presence in the local list.

            if is_smart:
                tag = " | ".join(reasons)
                print(f"{prefix}  {G}✓ SMART  {DIM}({tag}){RST}")
                results.append({
                    "address": addr,
                    "ui_amount": ui_amount,
                    "reasons": reasons,
                })
            else:
                print(f"{prefix}  {DIM}· regular{RST}")

        return results

    def _fetch_token_holders_silent(self, token_address: str, chain: Chain, limit: int) -> list | None:
        """Silent version of fetching token holders"""
        if chain == Chain.SOLANA:
            return self.api.get_token_holders_paginated(token_address, chain, total=limit)
        else:
            return self.moralis.get_token_holders_paginated(token_address, chain, total=limit)

    def _evaluate_holders_silent(self, holders: list, smart_set: set) -> List[Dict]:
        """Silent version of fetching smart wallets from the holders list"""
        results = []
        for holder in holders:
            addr = holder.get("owner", "???")
            ui_amount = holder.get("ui_amount", 0.0)

            if addr in smart_set or addr.lower() in smart_set:
                results.append({
                    "address": addr,
                    "ui_amount": ui_amount,
                })
        return results

    # ── Phase 4: Report ───────────────────────────────────────────

    def _print_report(self, token: str, chain: Chain,
                      smart: List[Dict], total: int):
        print()
        print(f"{M}{'═' * 56}{RST}")
        print(f"{M}  🧠  S M A R T   M O N E Y   R E P O R T{RST}")
        print(f"{M}{'═' * 56}{RST}")
        print(f"  Token   : {token[:20]}…{token[-6:]}")
        print(f"  Chain   : {chain.value.upper()}")
        print(f"  Scanned : {total} top holders")
        print(f"{M}{'─' * 56}{RST}")

        if not smart:
            print(f"\n  {W}No smart money wallets detected in the top {total} holders.{RST}")
        else:
            pct = (len(smart) / total) * 100 if total else 0
            total_balance = sum(w["ui_amount"] for w in smart)

            print(f"\n  {G}🟢 {len(smart)} Smart Wallets Found{RST}  ({pct:.0f}% of top holders)")
            print(f"  {C}💰 Combined Balance:{RST}  {total_balance:,.2f} tokens")

            # Top wallets table
            smart.sort(key=lambda w: w["ui_amount"], reverse=True)
            print(f"\n  {W}Top Smart Wallets:{RST}")
            print(f"  {'─' * 52}")
            for j, w in enumerate(smart[:5], 1):
                addr = w["address"]
                tags = " ".join(w["reasons"])
                print(f"  {j}. {addr}")
                print(f"     Balance: {w['ui_amount']:,.2f}  |  {DIM}{tags}{RST}")

        print(f"\n{M}{'═' * 56}{RST}")
        pages = (total + 99) // 100
        print(f"  {DIM}API calls: {pages} (token/holder only){RST}\n")

    # ── Helper ────────────────────────────────────────────────────

    def _banner(self, token: str, chain: Chain, limit: int):
        print(f"\n{C}{'━' * 56}{RST}")
        print(f"{C}  🔍  SMART MONEY SCANNER{RST}")
        print(f"{C}{'━' * 56}{RST}")
        print(f"  Token : {token}")
        print(f"  Chain : {chain.value.upper()}")
        print(f"  Limit : Top {limit} holders")
        print(f"  Rate  : 1 req/sec (Standard tier)")
        print(f"{C}{'━' * 56}{RST}")
