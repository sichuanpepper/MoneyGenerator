def risk_filter(sig):

    if sig is None:
        return False

    score = sig.get("score", 0)
    rsi = sig.get("rsi", None)
    sig_type = sig.get("type", "HOLD")

    if sig_type == "HOLD":
        return False

    if score < 55:
        return False

    if rsi is not None:
        if rsi > 88 or rsi < 12:
            return False

    if sig_type in ["BUY", "SELL"] and score < 60:
        return False

    return True