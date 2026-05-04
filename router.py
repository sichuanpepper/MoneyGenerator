from risk_engine import risk_filter


class Router:

    def __init__(self, slack_fn=None):
        self.slack_fn = slack_fn

    # =========================
    # MAIN ENTRY
    # =========================
    def route(self, symbol, sig):

        # 1. no signal
        if sig is None:
            return "NO_SIGNAL"

        # 2. meta log always allowed
        self.print_meta(symbol, sig)

        # 3. risk filter
        if not risk_filter(sig):
            print(f"🧯 FILTERED {symbol}")
            return "FILTERED"

        # 4. route actions
        sig_type = sig["type"]

        if sig_type in ["STRONG BUY", "STRONG SELL"]:
            self.send_alert(symbol, sig)
            return "ALERT_STRONG"

        if sig_type in ["BUY", "SELL"]:
            self.send_alert(symbol, sig)
            return "ALERT_NORMAL"

        return "HOLD"

    # =========================
    # META OUTPUT
    # =========================
    def print_meta(self, symbol, sig):

        print(f"""
📊 STOCK META {symbol}

Signal: {sig['type']}
Score: {sig['score']}
Price: {sig['price']}
RSI: {sig['rsi']}

Reasons:
{', '.join(sig.get('reasons', []))}
""")

    # =========================
    # SLACK ALERT
    # =========================
    def send_alert(self, symbol, sig):

        if not self.slack_fn:
            return

        msg = f"""
🚨 TRADE ALERT {symbol}

Signal: {sig['type']}
Score: {sig['score']}
Price: {sig['price']}
RSI: {sig['rsi']}

Reasons:
{', '.join(sig.get('reasons', []))}
"""

        self.slack_fn(msg)
        print(f"🚨 SLACK SENT {symbol}")