import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Configuration ───────────────────────────────────────────
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")

BIRDEYE_BASE_URL = "https://public-api.birdeye.so"

# Rate Limiting: Standard package = 1 Request Per Second
REQUEST_DELAY_SECONDS = 1.2  # Slightly over 1s for safety
REQUEST_DELAY_SECONDS = 1.2  # Slightly over 1s for safety

# ─── Smart Money Criteria ────────────────────────────────────────
# A wallet in the token's top traders is considered "Smart Money" if:
#   1. It appears on the global Gainers/Losers leaderboard (proven profitable), OR
#   2. Its trading volume in the token exceeds the whale threshold below.

# For the hardcoded smart wallet lists:
SMART_WALLETS_SOLANA_FILE = os.path.join(os.path.dirname(__file__), "smart_wallets_solana.json")
SMART_WALLETS_EVM_FILE = os.path.join(os.path.dirname(__file__), "smart_wallets_evm.json")

# For volume-based whale detection on the token itself:
WHALE_VOLUME_USD = 50000.0       # Min USD volume in the token to be classified as a whale
MIN_TRADE_COUNT = 3              # Min trades to avoid single lucky flips

# Top traders to analyze per token scan:
DEFAULT_TRADER_LIMIT = 20
