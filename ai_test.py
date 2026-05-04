from ai_dual_layer import analyze_trade

ind = {
    "price": 82.5,
    "sma50": 78.2,
    "sma200": 65.4,
    "rsi": 64.1
}

result = analyze_trade(
    symbol="RKLB",
    market="BULL",
    ind=ind,
    iv=44.8,
    signal="CALL SPREAD"
)

print(result["source"])
print(result["analysis"])