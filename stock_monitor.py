import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv
import pandas as pd

# =========================
# Init
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_STOCK")
STATE_FILE = "state_v3.json"
WATCHLIST_FILE = "watchlist_stock.json"

# =========================
# AI Engine
# =========================
def llama3_audit(symbol, market, short_data, long_data, final_signal):
    """
    Llama3 Audit with standardized English tags.
    """
    vol_ratio = short_data.get('vol_ratio', 1.0)
    
    # 强化后的英文 Prompt
    prompt = f"""
    [System: Financial Risk Auditor]
    Analyze the following trade setup for {symbol}:
    - Market Context: {market}
    - Signal: {final_signal}
    - Technicals: RSI={short_data.get('rsi')}, Volume Ratio={vol_ratio}x
    - Short-Term Logic: {short_data.get('reasons')}
    - Long-Term Trend: {long_data.get('signal')}

    Instructions:
    1. Start your response with one exact tag: [Strongly Agree], [Agree], [Disagree], or [Strongly Disagree].
    2. Provide a 1-2 sentence concise justification.
    3. Be skeptical. Check if Volume Ratio supports the price move and if RSI is at extremes.
    """
    
    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # 进一步降低随机性，确保审计结果的一致性
                    "num_predict": 100    # 限制输出长度，保持简洁
                }
            },
            timeout=60
        )
        return res.json().get("response", "N/A")
    except Exception as e:
        return f"Llama3 Audit Error: {str(e)}"

# =========================
# Utils & JSON Fix
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
        except:
            print("Slack notify error")

def load_state():
    if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0:
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_symbols():
    if os.path.exists(WATCHLIST_FILE) and os.path.getsize(WATCHLIST_FILE) > 0:
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f).get("symbols", [])
        except: return []
    return []

def fmt(x, d=2):
    """通用格式化，兼容 Series 和 Scalar"""
    val = x.iloc[0] if hasattr(x, "iloc") else x
    return round(float(val), d)

# =========================
# Indicators
# =========================
def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

def get_market():
    data = yf.download("SPY", period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "UNKNOWN"
    
    close = data["Close"].squeeze()
    data["SMA50"] = close.rolling(50).mean()
    data["SMA200"] = close.rolling(200).mean()
    
    last = data.iloc[-1]
    prev = data.iloc[-2]

    p = float(last["Close"].iloc[0]) if hasattr(last["Close"], "iloc") else float(last["Close"])
    s50 = float(last["SMA50"].iloc[0]) if hasattr(last["SMA50"], "iloc") else float(last["SMA50"])
    s200 = float(last["SMA200"].iloc[0]) if hasattr(last["SMA200"], "iloc") else float(last["SMA200"])
    ps200 = float(prev["SMA200"].iloc[0]) if hasattr(prev["SMA200"], "iloc") else float(prev["SMA200"])

    if p > s200 and s50 > s200 and s200 > ps200: return "BULL"
    if p < s200 and s50 < s200: return "BEAR"
    return "NEUTRAL"

# =========================
# Strategies
# =========================
def long_term(symbol):
    data = yf.download(symbol, period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "NEUTRAL", {}

    close = data["Close"].squeeze()
    s50 = close.rolling(50).mean()
    s200 = close.rolling(200).mean()
    last = data.iloc[-1]

    p, v50, v200 = fmt(last["Close"]), fmt(s50.iloc[-1]), fmt(s200.iloc[-1])
    sig = "BULLISH" if p > v200 and v50 > v200 else ("BEARISH" if p < v200 else "NEUTRAL")
    return sig, {"price": p, "sma50": v50, "sma200": v200, "signal": sig}

def short_term(symbol):
    data = yf.download(symbol, period="5d", interval="5m", progress=False)
    if data.empty: return "HOLD", {}

    close = data["Close"].squeeze()
    volume = data["Volume"].squeeze()
    
    m20 = close.rolling(20).mean()
    m50 = close.rolling(50).mean()
    r_val = rsi_calc(close)
    
    # 获取成交量异动：当前 vs 过去20个周期均值
    curr_vol = float(volume.iloc[-1])
    avg_vol = float(volume.iloc[-21:-1].mean()) # 不含最后一根
    vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    last = data.dropna().iloc[-1]
    p, v20, v50, rv = fmt(last["Close"]), fmt(m20.iloc[-1]), fmt(m50.iloc[-1]), fmt(r_val.iloc[-1], 1)

    score = 0
    reasons = []
    if v20 > v50: score += 1; reasons.append("MA20 > MA50")
    else: score -= 1; reasons.append("MA20 < MA50")
    
    if p > v20: score += 1; reasons.append("Price above MA20")
    else: score -= 1; reasons.append("Price below MA20")

    if rv < 35: score += 1; reasons.append("RSI oversold")
    elif rv > 70: score -= 2; reasons.append("RSI overbought")
    
    # 逻辑加分：放量上涨或缩量回调
    if vol_ratio > 2.0: reasons.append(f"Volume Surge ({vol_ratio}x)")

    ind = {"price": p, "ma20": v20, "ma50": v50, "rsi": rv, "vol_ratio": vol_ratio, "reasons": reasons}
    sig = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")
    return sig, ind

def fuse(short, long, market):
    if market == "BEAR":
        return "STRONG SELL" if short == "SELL" else ("BLOCKED BUY" if short == "BUY" else "HOLD")
    if market == "NEUTRAL":
        return "WEAK BUY" if (short == "BUY" and long == "BULLISH") else ("SELL" if short == "SELL" else "HOLD")
    if market == "BULL":
        return "STRONG BUY" if (short == "BUY" and long == "BULLISH") else ("WEAK SELL" if short == "SELL" else "HOLD")
    return "HOLD"

def position(signal, market):
    maps = {
        "BULL": {"STRONG BUY": 80, "WEAK BUY": 60, "HOLD": 40, "WEAK SELL": 20},
        "BEAR": {"STRONG SELL": 0, "SELL": 10, "HOLD": 20, "BLOCKED BUY": 10}
    }
    return maps.get(market, {"BUY": 40, "HOLD": 30, "SELL": 20}).get(signal, 30)

# =========================
# Main
# =========================
def run():
    state = load_state()
    EASTERN = pytz.timezone("US/Eastern")
    send_slack("🚀 STOCK MONITOR V3.3 (VOLUME ENABLED) STARTED")

    while True:
        try:
            symbols = load_symbols()
            market = get_market()
            now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S ET")

            for s in symbols:
                short_sig, short_ind = short_term(s)
                long_sig, long_ind = long_term(s)
                
                if not short_ind or not long_ind: continue

                final = fuse(short_sig, long_sig, market)
                pos = position(final, market)
                prev = state.get(s, {})

                if prev.get("signal") != final:
                    # 🤖 AI Audit (现在包含 vol_ratio)
                    ai_audit = llama3_audit(s, market, short_ind, long_ind, final)

                    # 格式化输出，加入成交量分析
                    vol_icon = "🔥" if short_ind['vol_ratio'] > 2.0 else ""
                    msg = f"""
📊 {s}   |   ⏰ {now}

🌎 Market: {market}

📉 Short-Term
- Signal: {short_sig}
- RSI: {short_ind.get('rsi')}
- Volume: {short_ind.get('vol_ratio')}x {vol_icon}
- MA20: {short_ind.get('ma20')}
- MA50: {short_ind.get('ma50')}
- Notes: {', '.join(short_ind.get('reasons', []))}

📈 Long-Term
- Signal: {long_sig}
- Price: {long_ind.get('price')}
- SMA50: {long_ind.get('sma50')}
- SMA200: {long_ind.get('sma200')}

👉 FINAL: {final}
💰 POSITION: {pos}%

🤖 LLAMA3 AUDIT:
{ai_audit}
"""
                    send_slack(msg)
                    print(msg)
                    state[s] = {"signal": final, "position": pos}

            save_state(state)
            time.sleep(300)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()