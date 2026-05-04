import yfinance as yf
import numpy as np

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def short_term(symbol):
    data = yf.download(symbol, period="5d", interval="5m")

    if data.empty:
        return "HOLD", {}

    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["RSI"] = rsi(data["Close"])

    data = data.dropna()
    last = data.iloc[-1]

    price = float(last["Close"])
    ma20 = float(last["MA20"])
    ma50 = float(last["MA50"])
    rsi_val = float(last["RSI"])

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


def long_term(symbol):
    data = yf.download(symbol, period="1y", interval="1d")

    if data.empty or len(data) < 200:
        return "NEUTRAL", {}

    data["SMA50"] = data["Close"].rolling(50).mean()
    data["SMA200"] = data["Close"].rolling(200).mean()

    data = data.dropna()
    last = data.iloc[-1]

    price = float(last["Close"])
    sma50 = float(last["SMA50"])
    sma200 = float(last["SMA200"])

    if price > sma200 and sma50 > sma200:
        return "BULLISH", {"price": price, "sma50": sma50, "sma200": sma200}

    if price < sma200:
        return "BEARISH", {"price": price, "sma50": sma50, "sma200": sma200}

    return "NEUTRAL", {"price": price, "sma50": sma50, "sma200": sma200}


def fuse(short, long, market):
    if market == "BEAR":
        if short == "BUY":
            return "BLOCKED BUY"
        if short == "SELL":
            return "STRONG SELL"
        return "HOLD"

    if market == "BULL":
        if short == "BUY" and long == "BULLISH":
            return "STRONG BUY"
        if short == "SELL":
            return "WEAK SELL"
        return "HOLD"

    return "HOLD"