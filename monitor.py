import yfinance as yf
import requests
import os
import json
import time
from dotenv import load_dotenv
from datetime import datetime
import pytz

# =========================
# Init
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_STOCK")

STATE_FILE = "state_v3.json"
WATCHLIST_FILE = "watchlist_stock.json"


# =========================
# Utils
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"text": msg})


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(state):
    json.dump(state, open(STATE_FILE, "w"), indent=2)


def load_symbols():
    if os.path.exists(WATCHLIST_FILE):
        return json.load(open(WATCHLIST_FILE)).get("symbols", [])
    return []


def fmt(x, d=2):
    return round(float(x), d)


# =========================
# RSI
# =========================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# =========================
# Market (SPY)
# =========================
def get_market():

    data = yf.download("SPY", period="1y", interval="1d")

    if data.empty or len(data) < 200:
        return "UNKNOWN"

    data["SMA50"] = data["Close"].rolling(50).mean()
    data["SMA200"] = data["Close"].rolling(200).mean()
    data = data.dropna()

    last = data.iloc[-1]
    prev = data.iloc[-2]

    price = float(last["Close"].iloc[0])
    sma50 = float(last["SMA50"].iloc[0])
    sma200 = float(last["SMA200"].iloc[0])
    prev_sma200 = float(prev["SMA200"].iloc[0])

    if price > sma200 and sma50 > sma200 and sma200 > prev_sma200:
        return "BULL"
    elif price < sma200 and sma50 < sma200:
        return "BEAR"
    return "NEUTRAL"


# =========================
# Long-term
# =========================
def long_term(symbol):

    data = yf.download(symbol, period="1y", interval="1d")

    if data.empty or len(data) < 200:
        return "NEUTRAL", {}

    data["SMA50"] = data["Close"].rolling(50).mean()
    data["SMA200"] = data["Close"].rolling(200).mean()
    data = data.dropna()

    last = data.iloc[-1]

    price = fmt(last["Close"].iloc[0])
    sma50 = fmt(last["SMA50"].iloc[0])
    sma200 = fmt(last["SMA200"].iloc[0])

    if price > sma200 and sma50 > sma200:
        return "BULLISH", {"price": price, "sma50": sma50, "sma200": sma200}
    elif price < sma200:
        return "BEARISH", {"price": price, "sma50": sma50, "sma200": sma200}
    else:
        return "NEUTRAL", {"price": price, "sma50": sma50, "sma200": sma200}


# =========================
# Short-term
# =========================
def short_term(symbol):

    data = yf.download(symbol, period="5d", interval="5m")

    if data.empty:
        return "HOLD", {}

    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["RSI"] = rsi(data["Close"])
    data = data.dropna()

    last = data.iloc[-1]

    price = fmt(last["Close"].iloc[0])
    ma20 = fmt(last["MA20"].iloc[0])
    ma50 = fmt(last["MA50"].iloc[0])
    rsi_val = fmt(last["RSI"].iloc[0], 1)

    score = 0
    reasons = []

    if ma20 > ma50:
        score += 1
        reasons.append("MA20 > MA50")
    else:
        score -= 1
        reasons.append("MA20 < MA50")

    if price > ma20:
        score += 1
        reasons.append("Price above MA20")
    else:
        score -= 1
        reasons.append("Price below MA20")

    if rsi_val < 30:
        score += 1
        reasons.append("RSI oversold")
    elif rsi_val > 70:
        score -= 2
        reasons.append("RSI overbought")

    indicators = {
        "price": price,
        "ma20": ma20,
        "ma50": ma50,
        "rsi": rsi_val,
        "reasons": reasons
    }

    if score >= 2:
        return "BUY", indicators
    elif score <= -2:
        return "SELL", indicators
    return "HOLD", indicators


# =========================
# Fusion
# =========================
def fuse(short, long, market):

    if market == "BEAR":
        if short == "BUY":
            return "BLOCKED BUY"
        if short == "SELL":
            return "STRONG SELL"
        return "HOLD"

    if market == "NEUTRAL":
        if short == "BUY" and long == "BULLISH":
            return "WEAK BUY"
        if short == "SELL":
            return "SELL"
        return "HOLD"

    if market == "BULL":
        if short == "BUY" and long == "BULLISH":
            return "STRONG BUY"
        if short == "SELL":
            return "WEAK SELL"
        return "HOLD"

    return "HOLD"


# =========================
# Position
# =========================
def position(signal, market):

    if market == "BULL":
        return {
            "STRONG BUY": 80,
            "WEAK BUY": 60,
            "HOLD": 40,
            "WEAK SELL": 20
        }.get(signal, 30)

    if market == "BEAR":
        return {
            "STRONG SELL": 0,
            "SELL": 10,
            "HOLD": 20,
            "BLOCKED BUY": 10
        }.get(signal, 10)

    return {
        "BUY": 40,
        "HOLD": 30,
        "SELL": 20
    }.get(signal, 30)


# =========================
# Main
# =========================
def run():

    state = load_state()
    send_slack("🚀 V3 SYSTEM STARTED (CLEAN VERSION)")
    
    EASTERN = pytz.timezone("US/Eastern")

    now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S ET")

    while True:

        symbols = load_symbols()
        market = get_market()

        for s in symbols:

            short_sig, short_ind = short_term(s)
            long_sig, long_ind = long_term(s)

            final = fuse(short_sig, long_sig, market)
            pos = position(final, market)

            prev = state.get(s, {})

            if prev.get("signal") != final or prev.get("position") != pos:

                msg = f"""
📊 {s}   |   ⏰ {now}

🌎 Market: {market}

📉 Short-Term
- Signal: {short_sig}
- RSI: {short_ind.get('rsi')}
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
"""

                send_slack(msg)

                state[s] = {
                    "signal": final,
                    "position": pos
                }

        save_state(state)
        time.sleep(300)


if __name__ == "__main__":
    run()
