import yfinance as yf
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# =========================
# INIT
# =========================
load_dotenv()

WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_OPTION")
WATCHLIST_FILE = "watchlist_option.json"
STATE_FILE = "portfolio_state.json"


# =========================
# SLACK
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        import requests
        requests.post(WEBHOOK_URL, json={"text": msg})


# =========================
# STATE
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# =========================
# WATCHLIST
# =========================
def load_symbols():
    if os.path.exists(WATCHLIST_FILE):
        return json.load(open(WATCHLIST_FILE)).get("symbols", [])
    return []


# =========================
# MARKET REGIME
# =========================
def get_market():

    df = yf.download("SPY", period="1y", interval="1d")

    df["SMA200"] = df["Close"].rolling(200).mean()
    df = df.dropna()

    last = df.iloc[-1]

    price = float(last["Close"])
    sma200 = float(last["SMA200"])

    return "BULL" if price > sma200 else "BEAR"


# =========================
# INDICATORS
# =========================
def indicators(df):

    df = df.copy()

    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    df = df.dropna()

    last = df.iloc[-1]

    return {
        "price": float(last["Close"]),
        "sma50": float(last["SMA50"]),
        "sma200": float(last["SMA200"]),
        "rsi": float(last["RSI"])
    }


# =========================
# IV RANK
# =========================
def iv_rank(df):

    returns = df["Close"].pct_change().dropna()
    vol = returns.rolling(20).std().dropna()

    if len(vol) < 5:
        return 50.0

    vol = vol.squeeze()

    current = float(vol.iloc[-1])
    low = float(vol.min())
    high = float(vol.max())

    if high == low:
        return 50.0

    return round((current - low) / (high - low) * 100, 1)


# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(ind, vol, market):

    price = ind["price"]
    sma200 = ind["sma200"]
    rsi = ind["rsi"]

    trend = "BULLISH" if price > sma200 else "BEARISH"

    if vol > 70:
        return "STRADDLE", ["High IV"]

    if market == "BULL" and trend == "BULLISH":
        return ("BUY CALL" if rsi < 60 else "CALL SPREAD"), ["Bull trend"]

    if market == "BEAR" and trend == "BEARISH":
        return "BUY PUT", ["Bear trend"]

    if rsi < 30:
        return "CALL REBOUND", ["Oversold"]

    return "HOLD", ["No edge"]


# =========================
# OPTIONS CONSTRUCTION ENGINE
# =========================
def build_trade(symbol, signal, price, market):

    atm = round(price)

    def dte():
        return "45DTE" if market == "BULL" else "30DTE"

    if signal == "CALL SPREAD":
        return {
            "type": "BULL CALL SPREAD",
            "buy": f"{symbol} {atm}C",
            "sell": f"{symbol} {atm+5}C",
            "dte": dte()
        }

    if signal == "BUY CALL":
        return {
            "type": "LONG CALL",
            "buy": f"{symbol} {atm}C",
            "dte": dte()
        }

    if signal == "BUY PUT":
        return {
            "type": "LONG PUT",
            "buy": f"{symbol} {atm}P",
            "dte": dte()
        }

    return {"type": "NO TRADE"}


# =========================
# PORTFOLIO ENGINE
# =========================
def position_size(market, signal):

    base = {
        "BULL": 25,
        "BEAR": 15
    }.get(market, 20)

    if "SPREAD" in signal:
        return base + 10
    if "LONG" in signal:
        return base

    return 10


# =========================
# MAIN ENGINE
# =========================
def run():

    state = load_state()

    send_slack("🚀 OPTIONS PORTFOLIO ENGINE STARTED")

    while True:

        symbols = load_symbols()
        market = get_market()

        portfolio_risk = 0

        for s in symbols:

            df = yf.download(s, period="1y", interval="1d")

            if df.empty or len(df) < 200:
                continue

            ind = indicators(df)
            vol = iv_rank(df)

            signal, reason = generate_signal(ind, vol, market)

            trade = build_trade(s, signal, ind["price"], market)

            size = position_size(market, signal)

            # =========================
            # RISK CONTROL
            # =========================
            if portfolio_risk > 100:
                continue

            portfolio_risk += size

            prev = state.get(s, {})

            if prev.get("signal") != signal:

                msg = f"""
========================
📊 OPTIONS PORTFOLIO ENGINE

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Symbol: {s}
Market: {market}

Price: {ind['price']:.2f}
RSI: {ind['rsi']:.1f}
IV Rank: {vol}

👉 Signal: {signal}
💰 Position Size: {size}%

🧠 Trade:
{trade}

Reason:
- {"; ".join(reason)}
========================
"""

                print(msg)
                send_slack(msg)

                state[s] = {"signal": signal}

        save_state(state)

        time.sleep(300)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    run()