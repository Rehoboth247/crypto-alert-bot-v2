# 🚀 Crypto Alert Bot

Monitor Dexscreener for new token pairs and get AI-powered alerts on Telegram.

## Features

- **Dexscreener Monitoring**: Selenium-based scraping of filtered new pairs
- **Smart Polling**: Checks 6x/day at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
- **Daily Reset**: Database clears at midnight for fresh tracking
- **AI Analysis**: DuckDuckGo search + Groq LLM (Llama 3.1) for narrative analysis
- **Telegram Alerts**: Rich alerts with metrics, chain, and AI summary

## Filter Criteria

- Min Liquidity: $60,000
- Min Market Cap: $300,000
- Max FDV: $10,000,000,000
- Min 24h Buys: 2
- Min 24h Sells: 2
- Min 24h Volume: $2,000,000
- Min 24h Change: 20%
- Min 6h Change: 5%
- Must have social profile (Twitter)

## Setup

### 1. Environment Variables

Create a `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_channel_id
GROQ_API_KEY=your_groq_api_key
```

Get your Groq API key from: https://console.groq.com

### 2. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

### 3. Railway Deployment

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Deploy crypto alert bot"
   git push origin main
   ```

2. **Create Railway Project**
   - Go to [railway.app](https://railway.app)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository

3. **Set Environment Variables**
   - In Railway dashboard, go to "Variables"
   - Add: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GROQ_API_KEY`

4. **Deploy**
   - Railway auto-deploys on push
   - Check logs for startup confirmation

## Alert Format

```
🚨 New Token Alert: TokenName ($SYMBOL)
⛓️ Chain: SOLANA

💰 Liquidity: $150.0K
📊 Market Cap: $2.5M
📈 24h Volume: $5.0M
🟢 24h Change: +45.2%
🟢 6h Change: +12.3%

📖 Narrative: AI/Gaming
🧠 Verdict: Product

📝 AI-generated summary about the token...

🔗 Dexscreener: https://dexscreener.com/...
🐦 Twitter: https://twitter.com/...
```

## Tech Stack

- Python 3.11+
- Selenium + Chrome (headless)
- DuckDuckGo Search (free, no API key)
- Groq API (Llama 3.1)
- SQLite database
- python-telegram-bot

## License

MIT
