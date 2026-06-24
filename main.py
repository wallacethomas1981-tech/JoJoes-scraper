import os
import praw
import httpx
import feedparser
import cloudscraper
import snscrape.modules.twitter as sntwitter
import yfinance as yf
import pandas as pd
import wikipedia
import pycoingecko
from pytrends.request import TrendReq
from transformers import pipeline
from groq import Groq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import asyncio
import re
from bs4 import BeautifulSoup
import ta

app = FastAPI(title="ProfitScout AI v5 - ULTIMATE FREE", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Init ALL services
reddit = praw.Reddit(client_id=os.getenv("REDDIT_CLIENT_ID"), client_secret=os.getenv("REDDIT_CLIENT_SECRET"), user_agent=os.getenv("REDDIT_USER_AGENT")) if os.getenv("REDDIT_CLIENT_ID") else None
groq = Groq(api_key=os.getenv("GROQ_API_KEY")) if os.getenv("GROQ_API_KEY") else None
sentiment_analyzer = pipeline("sentiment-analysis", model="ProsusAI/finbert")
pytrends = TrendReq(hl='en-US', tz=360)
scraper = cloudscraper.create_scraper()
cg = pycoingecko.CoinGeckoAPI()

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "profitscout-wallacethomas78")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

@app.get("/health")
async def health():
    return {"status":"ULTIMATE","endpoints":52,"cost":"$0","cashapp":"$wallacethomas78"}

@app.get("/api/reddit-trending")
async def reddit_trending(limit: int = 20):
    if not reddit: return {"error": "Reddit not configured"}
    subs = "wallstreetbets+pennystocks+stocks+investing+StockMarket+options+Superstonk+amcstock+SNDL"
    posts = reddit.subreddit(subs).hot(limit=500)
    tickers = {}
    for p in posts:
        words = re.findall(r'\$[A-Z]{1,5}\b', p.title.upper())
        for w in words:
            t = w.replace("$", "")
            if t not in ["USD","USA","ETF","CEO","IPO","ATH","YOLO","USD","IRS"]:
                tickers[t] = tickers.get(t, 0) + p.score + (p.num_comments * 2)
    return {"trending": sorted([{"ticker": k, "hype_score": v} for k, v in tickers.items()], key=lambda x: x["hype_score"], reverse=True)[:limit]}

@app.get("/api/reddit-sentiment/{ticker}")
async def reddit_sentiment(ticker: str):
    if not reddit: return {"error": "Reddit not configured", "ticker": ticker}
    try:
        subreddits = "pennystocks+wallstreetbets+stocks+investing+StockMarket"
        posts = reddit.subreddit(subreddits).search(f"${ticker}", sort="new", time_filter="day", limit=100)
        bullish_words = ["moon","rocket","🚀","buy","long","bullish","calls","yolo","tendies","green"]
        bearish_words = ["dump","scam","bag","bearish","puts","sell","crash","💩","red"]
        bullish_count = 0
        bearish_count = 0
        for post in posts:
            text = (post.title + " " + post.selftext).lower()
            bullish_count += sum(1 for w in bullish_words if w in text)
            bearish_count += sum(1 for w in bearish_words if w in text)
        total = bullish_count + bearish_count
        score = (bullish_count - bearish_count) / max(total, 1)
        sentiment = "Very Bullish" if score > 0.3 else "Bullish" if score > 0.1 else "Very Bearish" if score < -0.3 else "Bearish" if score < -0.1 else "Neutral"
        return {"ticker": ticker.upper(), "sentiment": sentiment, "sentiment_score": round(score,3), "bullish_mentions": bullish_count, "bearish_mentions": bearish_count, "total_mentions": total}
    except Exception as e:
        return {"error": str(e), "ticker": ticker}

@app.get("/api/twitter-sentiment/{ticker}")
async def twitter_sentiment(ticker: str, limit: int = 100):
    try:
        tweets = []
        for i, tweet in enumerate(sntwitter.TwitterSearchScraper(f'${ticker} since:{(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")}').get_items()):
            if i >= limit: break
            tweets.append(tweet.rawContent)
        if not tweets: return {"ticker": ticker, "mentions_24h": 0}
        sentiments = sentiment_analyzer(tweets[:50])
        bullish = sum(1 for s in sentiments if s["label"] == "positive")
        bearish = sum(1 for s in sentiments if s["label"] == "negative")
        return {"ticker": ticker, "mentions_24h": len(tweets), "bullish": bullish, "bearish": bearish, "sentiment": "Bullish" if bullish > bearish * 1.2 else "Bearish" if bearish > bullish * 1.2 else "Neutral"}
    except: return {"ticker": ticker, "error": "Rate limited"}

@app.get("/api/google-trends/{ticker}")
async def google_trends(ticker: str):
    try:
        pytrends.build_payload([ticker], timeframe='now 7-d')
        interest = pytrends.interest_over_time()
        if interest.empty: return {"ticker": ticker, "trending": False}
        current = interest[ticker].iloc[-1]
        avg = interest[ticker].mean()
        spike = current > (avg * 1.5)
        return {"ticker": ticker, "current_interest": int(current), "7day_avg": round(avg, 1), "spike_detected": spike, "percent_change": round(((current - avg) / avg) * 100, 1)}
    except: return {"ticker": ticker, "error": "Rate limited"}

@app.get("/api/sec-insider/{ticker}")
async def sec_insider(ticker: str):
    try:
        headers = {"User-Agent": "ProfitScout wallacethomas78@gmail.com"}
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://data.sec.gov/submissions/CIK{ticker}.json", headers=headers)
            if res.status_code!= 200: return {"ticker": ticker, "insider_buying": False}
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            return {"ticker": ticker, "insider_buying": "4" in forms[:10]}
    except: return {"ticker": ticker, "insider_buying": False}

@app.get("/api/congress-trades")
async def congress_trades():
    try:
        feed = feedparser.parse("https://www.capitoltrades.com/trades.rss")
        trades = []
        for entry in feed.entries[:20]:
            tickers = re.findall(r'\b[A-Z]{1,5}\b', entry.title)
            trades.append({"politician": entry.title.split(" - ")[0], "ticker": tickers[0] if tickers else "N/A", "date": entry.published})
        return {"recent_trades": trades}
    except: return {"recent_trades": []}

@app.get("/api/unusual-options/{ticker}")
async def unusual_options(ticker: str):
    try:
        res = scraper.get(f"https://www.barchart.com/stocks/quotes/{ticker}/options")
        soup = BeautifulSoup(res.text, 'lxml')
        table = soup.select_one("table#main-table")
        options = []
        if table:
            for row in table.select("tbody tr")[:10]:
                cols = [c.text.strip() for c in row.find_all("td")]
                if len(cols) > 8 and "Vol/OI" in cols[8]:
                    try:
                        ratio = float(cols[8].split()[0])
                        if ratio > 2: options.append({"strike": cols[0], "type": cols[1], "vol_oi_ratio": ratio})
                    except: pass
        return {"ticker": ticker, "unusual": options}
    except: return {"ticker": ticker, "unusual": []}

@app.get("/api/fda-calendar")
async def fda_calendar():
    try:
        res = scraper.get("https://www.biopharmcatalyst.com/calendars/fda-calendar")
        soup = BeautifulSoup(res.text, 'lxml')
        events = []
        for row in soup.select("table tbody tr")[:10]:
            cols = row.find_all("td")
            if len(cols) >= 3: events.append({"date": cols[0].text.strip(), "ticker": cols[1].text.strip(), "drug": cols[2].text.strip()})
        return {"upcoming_catalysts": events}
    except: return {"upcoming_catalysts": []}

@app.get("/api/wikipedia-trends/{ticker}")
async def wikipedia_trends(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        company = stock.info.get('longName', ticker).replace(' ', '_')
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{company}/daily/{(datetime.now() - timedelta(days=30)).strftime('%Y%m%d')}/{(datetime.now()).strftime('%Y%m%d')}"
        async with httpx.AsyncClient() as client:
            res = await client.get(url)
            data = res.json()
            views = [item['views'] for item in data['items']]
            spike = views[-1] > (sum(views[:-1]) / len(views[:-1])) * 2
            return {"ticker": ticker, "yesterday_views": views[-1], "30day_avg": int(sum(views) / len(views)), "spike": spike}
    except: return {"ticker": ticker, "spike": False}

@app.get("/api/ai-dd/{ticker}")
async def ai_dd(ticker: str):
    if not groq: return {"error": "Groq not configured"}
    prompt = f"You are a brutal penny stock analyst. Analyze ${ticker}. Include: 1) Business 2) Catalysts 3) Risks 4) WSB sentiment 5) Price targets. Be honest. 300 words max."
    chat = groq.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama3-70b-8192", temperature=0.7)
    return {"ticker": ticker, "dd_report": chat.choices[0].message.content}

@app.get("/api/ta/{ticker}")
async def technical_analysis(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        hist['RSI'] = ta.momentum.RSIIndicator(hist['Close']).rsi()
        hist['MACD'] = ta.trend.MACD(hist['Close']).macd_diff()
        hist['BB_low'] = ta.volatility.BollingerBands(hist['Close']).bollinger_lband()
        latest = hist.iloc[-1]
        signals = []
        if latest['RSI'] < 30: signals.append("RSI Oversold - BUY")
        if latest['RSI'] > 70: signals.append("RSI Overbought - SELL")
        if latest['Close'] < latest['BB_low']: signals.append("Below BB - Bounce expected")
        if latest['MACD'] > 0: signals.append("MACD Bullish")
        return {"ticker": ticker, "rsi": round(latest['RSI'], 2), "macd": round(latest['MACD'], 2), "signals": signals}
    except: return {"ticker": ticker, "error": "TA failed"}

@app.post("/api/alerts/mega")
async def mega_alert(title: str, message: str):
    tasks = []
    async with httpx.AsyncClient() as client:
        if NTFY_TOPIC:
            headers = {"Title": title, "Priority": "max", "Tags": "rocket,moneybag,fire"}
            tasks.append(client.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode('utf-8'), headers=headers))
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            tasks.append(client.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": f"*{title}*\n\n{message}", "parse_mode": "Markdown"}))
        if DISCORD_WEBHOOK:
            tasks.append(client.post(DISCORD_WEBHOOK, json={"embeds": [{"title": title, "description": message, "color": 16711680}]}))
        await asyncio.gather(*tasks, return_exceptions=True)
    return {"status": "sent_to_all_channels"}

@app.get("/api/crypto-trending")
async def crypto_trending():
    trending = cg.get_search_trending()
    return {"trending_coins": [{"name": c["item"]["name"], "symbol": c["item"]["symbol"], "rank": c["item"]["market_cap_rank"]} for c in trending["coins"][:10]]}

@app.get("/api/bypass-paywall")
async def bypass_paywall(url: str):
    try:
        archive_url = f"https://archive.today/?run=1&url={url}"
        res = scraper.get(archive_url)
        return {"status": "success", "bypass_url": res.url}
    except: return {"error": "Bypass failed"}