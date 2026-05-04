import yfinance as yf
import numpy as np

def get_option_signal(symbol):

    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="3mo")

        if hist.empty or len(hist) < 30:
            return None

        # RSI
        delta = hist["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        rsi = 100 - (100 / (1 + gain.rolling(14).mean() / loss.rolling(14).mean()))

        hist["RSI"] = rsi
        hist["MA20"] = hist["Close"].rolling(20).mean()

        last = hist.iloc[-1]

        price = float(last["Close"])
        rsi_val = float(last["RSI"])
        ma20 = float(last["MA20"])

        expirations = stock.options
        if not expirations:
            return None

        expiry = expirations[0]
        chain = stock.option_chain(expiry)

        calls = chain.calls.copy()
        puts = chain.puts.copy()

        ivs = list(calls["impliedVolatility"]) + list(puts["impliedVolatility"])
        ivs = [x for x in ivs if x > 0]

        if len(ivs) < 5:
            return None

        iv_min, iv_max = min(ivs), max(ivs)
        iv_now = ivs[0]

        iv_rank = 0 if iv_max == iv_min else (iv_now - iv_min) / (iv_max - iv_min) * 100

        signal = None
        option = None

        # CALL
        if rsi_val < 35 and price > ma20 and iv_rank < 40:
            calls["dist"] = abs(calls["strike"] - price)
            option = calls.sort_values("dist").iloc[0]
            signal = "CALL"

        # PUT
        elif rsi_val > 65 and price < ma20 and iv_rank < 40:
            puts["dist"] = abs(puts["strike"] - price)
            option = puts.sort_values("dist").iloc[0]
            signal = "PUT"

        if not signal:
            return None

        return {
            "symbol": symbol,
            "type": signal,
            "price": round(price, 2),
            "rsi": round(rsi_val, 1),
            "iv_rank": round(iv_rank, 1),
            "strike": float(option["strike"]),
            "premium": float(option["lastPrice"]),
            "expiry": expiry
        }

    except Exception as e:
        print(f"option error {symbol}: {e}")
        return None