"""
Narrative Analyzer Module

Uses DuckDuckGo for web search (free, no API key) and Groq for fast LLM analysis.
"""

import os
import time
import requests
from typing import Optional

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

# Load environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def search_twitter_mentions(symbol: str, name: str) -> list[dict]:
    """
    Search for token mentions on Twitter/X using DuckDuckGo (free, no API key).
    """
    if DDGS is None:
        print("[NarrativeAnalyzer] Warning: duckduckgo-search not installed")
        return []
    
    query = f'{symbol} {name} crypto twitter'
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10))
        
        # Convert to same format as before
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "link": r.get("href", "")
            })
        
        print(f"[NarrativeAnalyzer] Found {len(formatted)} search results")
        return formatted
        
    except Exception as e:
        print(f"[NarrativeAnalyzer] DuckDuckGo search error: {e}")
        return []


def analyze_with_groq(token_info: dict, search_results: list[dict]) -> dict:
    """
    Analyze token narrative using Groq's fast LLM API.
    Uses Llama 3.1 8B model for quick responses.
    """
    if not GROQ_API_KEY:
        print("[NarrativeAnalyzer] Warning: GROQ_API_KEY not set")
        return {
            "narrative": "Unknown",
            "verdict": "Unknown",
            "summary": "Unable to analyze - API key not configured."
        }
    
    # Prepare search snippets
    snippets = []
    for result in search_results[:5]:
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        if title or snippet:
            snippets.append(f"- {title}: {snippet}")
    
    snippets_text = "\n".join(snippets) if snippets else "No search results found."
    
    token_name = token_info.get("name", "Unknown")
    token_symbol = token_info.get("symbol", "???")
    token_description = token_info.get("description", "No description available.")
    
    prompt = f"""Analyze this cryptocurrency token briefly.

Token: {token_name} (${token_symbol})
Description: {token_description}

Twitter Results:
{snippets_text}

Answer in this exact format:
VERDICT: [Product/Meme/Unclear]
NARRATIVE: [1-2 words: AI, Gaming, DeFi, Meme, Political, etc.]
SUMMARY: [One sentence about what this token is]"""

    # Call Groq API
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.2
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        analysis_text = data["choices"][0]["message"]["content"].strip()
        return parse_llm_response(analysis_text)
        
    except requests.RequestException as e:
        error_str = str(e)
        
        if "429" in error_str or "rate" in error_str.lower():
            print("[NarrativeAnalyzer] Groq rate limited, waiting 2s...")
            time.sleep(2)
            # Retry once
            try:
                response = requests.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "llama-3.1-8b-instant",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 150,
                        "temperature": 0.2
                    },
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                analysis_text = data["choices"][0]["message"]["content"].strip()
                return parse_llm_response(analysis_text)
            except Exception:
                pass
        
        print(f"[NarrativeAnalyzer] Groq API error: {e}")
        return {
            "narrative": "Error",
            "verdict": "Unknown",
            "summary": f"{token_name} - Analysis failed."
        }


def parse_llm_response(response_text: str) -> dict:
    """Parse the structured LLM response."""
    result = {
        "narrative": "Unknown",
        "verdict": "Unknown",
        "summary": response_text
    }
    
    lines = response_text.split("\n")
    
    for line in lines:
        line = line.strip()
        
        if line.upper().startswith("VERDICT:"):
            result["verdict"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("NARRATIVE:"):
            result["narrative"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("SUMMARY:"):
            result["summary"] = line.split(":", 1)[1].strip()
    
    return result


async def analyze_token_narrative(token_info: dict) -> dict:
    """
    Full narrative analysis pipeline for a token.
    Runs blocking I/O in an executor to avoid freezing the event loop.
    """
    import asyncio
    
    symbol = token_info.get("symbol", "")
    name = token_info.get("name", "")
    
    print(f"[NarrativeAnalyzer] Searching for {symbol} ({name}) on Twitter...")
    loop = asyncio.get_event_loop()
    search_results = await loop.run_in_executor(None, search_twitter_mentions, symbol, name)
    
    print(f"[NarrativeAnalyzer] Analyzing with Groq (Llama 3.1)...")
    analysis = await loop.run_in_executor(None, analyze_with_groq, token_info, search_results)
    
    return analysis
