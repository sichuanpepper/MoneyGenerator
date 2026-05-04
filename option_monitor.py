import yfinance as yf
import json
import os
import time
import requests
import pandas as pd
import pytz
from datetime import datetime
from dotenv import load_dotenv

# =========================
# Init
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_OPTION")
STATE_FILE = "portfolio_state.json"
WATCHLIST_FILE = "watchlist_option.json"

# =========================
# AI Engine (Updated with Attitude Tags)
# =========================
def llama3_audit(symbol, market, ind, vol_info, sig, trade):
    """调用本地 Llama3 进行期权策略审计，包含英文态度标签"""
    prompt = f"""
    [Expert Options Strategist & Auditor]
    Analyze this trade for {symbol}:
    - Market: {market} | Signal: {sig}
    - Technicals: Price={ind['price']}, RSI={ind['rsi']}, IV Rank={ind['iv_rank']}%
    - Volume: {vol_info['ratio']}x relative to 20-day avg
    - Strategy: {trade}

    Instructions:
    1. Start with one tag: [Strongly Agree], [Agree], [Disagree], or [Strongly Disagree].
    2. Provide 1-2 sentences of logic, specifically checking if Volume supports the Signal.
    3. Be critical of high RSI or low volume moves.
    """
    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 120}
            },
            timeout=20
        )
        return res.json().get("response", "N/A")
    except:
        return "Llama3 Audit Offline"

# =========================
# Utils
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        try: requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
        except: print("Slack notify error")

def load_state():
    if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0:
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)

def load_symbols():
    if os.path.exists(WATCHLIST_FILE) and os.path.getsize(WATCHLIST_FILE) > 0:
        try:
            with open(WATCHLIST_FILE, "r") as f: return json.load(f).get("symbols", [])
        except: return []
    return []

def fmt(x, d=2):
    val = x.iloc[0] if hasattr(x, "iloc") else x
    return round(float(val), d)

# =========================
# Advanced Indicators (Volume & IV)
# =========================
def get_market():
    data = yf.download("SPY", period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "UNKNOWN"
    close = data["Close"].squeeze()
    sma200 = close.rolling(200).mean()
    return "BULL" if fmt(close.iloc[-1]) > fmt(sma200.iloc[-1]) else "BEAR"

def analyze_stock(df):
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    
    # 指标计算
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean().replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    
    # IV Rank (基于历史波动率的简化版)
    pct_chg = close.pct_change().rolling(20).std().dropna()
    iv_r = 50.0
    if len(pct_chg) > 10:
        curr, lo, hi = fmt(pct_chg.iloc[-1]), fmt(pct_chg.min()), fmt(pct_chg.max())
        iv_r = round((curr - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0

    # Volume Analysis
    curr_vol = float(volume.iloc[-1])
    avg_vol = float(volume.iloc[-21:-1].mean())
    vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    return {
        "price": fmt(close.iloc[-1]),
        "sma200": fmt(sma200.iloc[-1]),
        "rsi": fmt(rsi.iloc[-1], 1),
        "iv_rank": iv_r,
        "vol_ratio": vol_ratio
    }

# =========================
# Strategy Logic
# =========================
def generate_signal(ind, market):
    p, s200, r, iv, vr = ind["price"], ind["sma200"], ind["rsi"], ind["iv_rank"], ind["vol_ratio"]
    reasons = []

    # 1. 高波动率保护
    if iv > 75: 
        return "STRADDLE", ["Extreme IV Rank - Volatility Play"]
    
    # 2. 多头市场逻辑
    if market == "BULL" and p > s200:
        if vr > 1.8 and r < 65: # 放量且未超买
            return "BUY CALL", ["Bull Market", "Volume Breakout"]
        if r > 70:
            return "CALL SPREAD", ["Bull Market", "Overbought - Hedged Play"]
        return "BUY CALL", ["Standard Bull Trend"]

    # 3. 空头/超跌逻辑
    if r < 25:
        return "CALL REBOUND", ["Deep Oversold", f"Vol Support: {vr}x"]
    
    if market == "BEAR" and p < s200:
        return "BUY PUT", ["Bear Market Momentum"]

    return "HOLD", ["No Edge"]

def build_trade(symbol, signal, price, market):
    atm = round(price)
    dte = "45DTE" if market == "BULL" else "30DTE"
    
    trades = {
        "BUY CALL": {"type": "LONG CALL", "buy": f"{symbol} {atm}C", "dte": dte},
        "CALL SPREAD": {"type": "BULL CALL SPREAD", "buy": f"{symbol} {atm}C", "sell": f"{symbol} {atm+5}C", "dte": dte},
        "BUY PUT": {"type": "LONG PUT", "buy": f"{symbol} {atm}P", "dte": dte},
        "STRADDLE": {"type": "LONG STRADDLE", "buy": f"{symbol} {atm}C + {atm}P", "dte": "21DTE"},
        "CALL REBOUND": {"type": "LONG CALL (REBOUND)", "buy": f"{symbol} {atm}C", "dte": "14DTE"}
    }
    return trades.get(signal, {"type": "NO TRADE"})

# =========================
# Execution Loop
# =========================
def run():
    state = load_state()
    EASTERN = pytz.timezone("US/Eastern")
    send_slack("🚀 OPTIONS MONITOR V3.3 (VOLUME & AI AUDIT) ONLINE")

    while True:
        try:
            symbols = load_symbols()
            market = get_market()
            now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S ET")

            for s in symbols:
                df = yf.download(s, period="1y", interval="1d", progress=False)
                if df.empty or len(df) < 200: continue

                ind = analyze_stock(df)
                sig, reasons = generate_signal(ind, market)
                
                # 只有当信号变化时才触发
                if state.get(s, {}).get("signal") != sig:
                    trade = build_trade(s, sig, ind["price"], market)
                    
                    # 🤖 AI Audit (态度 + 成交量分析)
                    ai_audit = llama3_audit(s, market, ind, {"ratio": ind['vol_ratio']}, sig, trade)

                    vol_icon = "🔥" if ind['vol_ratio'] > 2.0 else ""
                    msg = f"""
📊 {s}   |   ⏰ {now}
🌎 Market: {market}

📈 Indicators:
- Price: {ind['price']} | RSI: {ind['rsi']}
- IV Rank: {ind['iv_rank']}%
- Volume: {ind['vol_ratio']}x {vol_icon}

👉 FINAL SIGNAL: {sig}
🧠 Trade: {trade.get('type')}
- Action: {trade.get('buy', 'N/A')} {('/ ' + trade.get('sell')) if trade.get('sell') else ''}
- DTE: {trade.get('dte')} | Reason: {', '.join(reasons)}

🤖 LLAMA3 AUDIT:
{ai_audit}
"""
                    print(msg)
                    send_slack(msg)
                    state[s] = {"signal": sig}

            save_state(state)
            time.sleep(300) # 每5分钟检查一次
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()