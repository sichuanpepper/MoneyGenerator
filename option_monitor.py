import yfinance as yf
import json
import os
import time
import requests
import pandas as pd
import pytz
from datetime import datetime
from dotenv import load_dotenv
from ai_auditor import AIAuditor  # 导入统一审计类

# =========================
# Init
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_OPTION")
STATE_FILE = "option_state.json"
WATCHLIST_FILE = "watchlist_option.json"
EASTERN = pytz.timezone("US/Eastern")

auditor = AIAuditor() # 实例化统一审计员

# =========================
# Utils
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        try: requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
        except: print("Slack notify error")

def load_json(path, key=None):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return data.get(key, []) if key else data
        except: return [] if key else {}
    return [] if key else {}

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def fmt(x, d=2):
    if hasattr(x, "values"): val = x.values[-1] if len(x) > 0 else 0
    elif hasattr(x, "iloc"): val = x.iloc[-1]
    else: val = x
    return round(float(val), d)

# =========================
# Advanced Indicators (Volume & IV)
# =========================
def get_market():
    data = yf.download("SPY", period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "UNKNOWN"
    close = data["Close"].squeeze()
    sma200 = close.rolling(200).mean()
    return "BULL" if fmt(close) > fmt(sma200) else "BEAR"

def analyze_stock(df):
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    
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
        curr, lo, hi = fmt(pct_chg), pct_chg.min(), pct_chg.max()
        iv_r = round((curr - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0

    # Volume Analysis
    curr_vol = float(volume.values[-1])
    avg_vol = float(volume.iloc[-21:-1].mean())
    vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    return {
        "price": fmt(close),
        "rsi": fmt(rsi, 1),
        "iv_rank": iv_r,
        "vol_ratio": vol_ratio
    }

# =========================
# Strategy Logic (保持不变)
# =========================
def generate_signal(ind, market):
    p, r, iv, vr = ind["price"], ind["rsi"], ind["iv_rank"], ind["vol_ratio"]
    # 逻辑判断...
    if iv > 75: return "STRADDLE", ["Extreme IV Rank - Volatility Play"]
    if market == "BULL":
        if vr > 1.8 and r < 65: return "BUY CALL", ["Bull Market", "Volume Breakout"]
        if r > 70: return "CALL SPREAD", ["Overbought - Hedged Play"]
        return "BUY CALL", ["Standard Bull Trend"]
    if r < 25: return "CALL REBOUND", ["Deep Oversold"]
    if market == "BEAR": return "BUY PUT", ["Bear Market Momentum"]
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
    state = load_json(STATE_FILE)
    send_slack("🚀 OPTIONS MONITOR V3.3 (HYBRID AI AUDIT) ONLINE")

    while True:
        try:
            symbols = load_json(WATCHLIST_FILE, key="symbols")
            market = get_market()
            now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S ET")

            for s in symbols:
                df = yf.download(s, period="1y", interval="1d", progress=False)
                if df.empty or len(df) < 20: continue

                ind = analyze_stock(df)
                sig, reasons = generate_signal(ind, market)
                
                if state.get(s, {}).get("signal") != sig and sig != "HOLD":
                    trade = build_trade(s, sig, ind["price"], market)
                    
                    # 🤖 构造发送给 ai_auditor 的数据包
                    audit_payload = {
                        "symbol": s,
                        "strategy": trade.get('type'),
                        "underlying_price": ind['price'],
                        "strike": trade.get('buy', 'N/A'),
                        "expiry": trade.get('dte'),
                        "market": market,
                        "rsi": ind['rsi'],
                        "vol_ratio": ind['vol_ratio']
                    }

                    # 调用统一审计接口
                    print(f"🧐 Auditing Option Strategy for {s}...")
                    llama_res = auditor.audit('llama3', 'options', audit_payload)
                    gemini_res = auditor.audit('gemini', 'options', audit_payload)

                    vol_icon = "🔥" if ind['vol_ratio'] > 2.0 else ""
                    msg = f"""
📊 *{s}* | ⏰ {now} | 🌎 {market}

📈 Indicators:
- Price: ${ind['price']} | RSI: {ind['rsi']}
- IV Rank: {ind['iv_rank']}% | Vol: {ind['vol_ratio']}x {vol_icon}

👉 SIGNAL: *{sig}* ({trade.get('type')})
- Details: {trade.get('buy', 'N/A')} {('/ ' + trade.get('sell')) if trade.get('sell') else ''}
- Reason: {', '.join(reasons)}

🤖 *Llama3 (Local)*:
{llama_res}

🌟 *Gemini (Cloud)*:
{gemini_res}
"""
                    print(msg)
                    send_slack(msg)
                    state[s] = {"signal": sig}

            save_json(STATE_FILE, state)
            time.sleep(300)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()