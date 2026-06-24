import os
import httpx
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

app = FastAPI(title="ProfitScout Agent - GOD MODE")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
scheduler = AsyncIOScheduler()
SCRAPER_URL = os.getenv("SCRAPER_URL", "http://localhost:8000")

async def GOD_MODE_SCAN():
    watchlist = ["SNDL","AMC","BB","MULN","PROG","GME","NOK","PLTR","SOFI","TLRY","SPCE","WISH","CLOV","BBBY","APE"]
    async with httpx.AsyncClient(timeout=120.0) as client:
        for ticker in watchlist:
            signals = []
            tasks = [
                client.get(f"{SCRAPER_URL}/api/reddit-sentiment/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/twitter-sentiment/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/google-trends/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/sec-insider/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/unusual-options/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/wikipedia-trends/{ticker}"),
                client.get(f"{SCRAPER_URL}/api/ta/{ticker}"),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            try:
                if not isinstance(results[0], Exception) and results[0].json().get("total_mentions", 0) > 25: signals.append("🔥 WSB Exploding")
                if not isinstance(results[1], Exception) and results[1].json().get("sentiment") == "Bullish": signals.append("🐦 Twitter Bullish")
                if not isinstance(results[2], Exception) and results[2].json().get("spike_detected"): signals.append("📈 Google Spike")
                if not isinstance(results[3], Exception) and results[3].json().get("insider_buying"): signals.append("💼 Insider Buying")
                if not isinstance(results[4], Exception) and results[4].json().get("unusual"): signals.append("🎰 Unusual Options")
                if not isinstance(results[5], Exception) and results[5].json().get("spike"): signals.append("📚 Wikipedia Spike")
                if not isinstance(results[6], Exception) and "BUY" in str(results[6].json().get("signals", [])): signals.append("📊 TA Buy Signal")
            except: pass
            if len(signals) >= 4:
                msg = f"${ticker} GOD MODE ALERT!\n\n" + "\n".join(signals) + f"\n\n{len(signals)}/12 signals firing."
                await client.post(f"{SCRAPER_URL}/api/alerts/mega", params={"title": f"🚨🚨🚨 ${ticker} ALL SYSTEMS GO", "message": msg})

@app.on_event("startup")
async def startup():
    scheduler.add_job(GOD_MODE_SCAN, 'cron', day_of_week='mon-fri', hour='13-21', minute='*/1')
    scheduler.start()

@app.get("/health")
async def health():
    return {"status": "GOD MODE ACTIVE", "scan_interval": "60s", "signals": 12}