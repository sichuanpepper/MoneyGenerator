from data_layer import get_stock_df, add_indicators


def stock_signal(symbol):

    df = get_stock_df(symbol)

    if df is None or len(df) < 50:
        return None

    df = add_indicators(df)
    df = df.dropna()

    if len(df) < 5:
        return None

    last = df.iloc[-1]

    price = float(last["Close"])
    ma20 = float(last["MA20"])
    ma50 = float(last["MA50"])
    rsi = float(last["RSI"])

    score = 50
    reasons = []

    if ma20 > ma50:
        score += 15
        reasons.append("trend bullish")
    else:
        score -= 15
        reasons.append("trend bearish")

    if price > ma20:
        score += 15
        reasons.append("above MA20")
    else:
        score -= 10
        reasons.append("below MA20")

    if rsi < 30:
        score += 20
        reasons.append("oversold")
    elif rsi > 70:
        score -= 25
        reasons.append("overbought")

    if score >= 70:
        sig = "STRONG BUY"
    elif score >= 60:
        sig = "BUY"
    elif score <= 30:
        sig = "STRONG SELL"
    elif score <= 20:
        sig = "SELL"
    else:
        sig = "HOLD"

    return {
        "type": sig,
        "score": score,
        "price": price,
        "rsi": rsi,
        "ma20": ma20,
        "ma50": ma50,
        "reasons": reasons
    }