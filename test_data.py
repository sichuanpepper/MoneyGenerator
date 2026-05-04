import yfinance as yf

data = yf.download("AAPL", period="3mo", interval="1d")
print(data.tail())
