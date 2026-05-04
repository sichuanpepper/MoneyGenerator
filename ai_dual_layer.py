import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# =========================
# OpenAI Client
# =========================
client = OpenAI()


# =========================
# Llama3（本地）
# =========================
def llama3_analysis(symbol, market, ind, iv, signal):

    prompt = f"""
You are a professional options risk analyst.

Symbol: {symbol}
Market: {market}

Price: {ind['price']:.2f}
SMA50: {ind['sma50']:.2f}
SMA200: {ind['sma200']:.2f}
RSI: {ind['rsi']:.1f}
IV Rank: {iv}

Signal: {signal}

Evaluate:
1. Risk Level (LOW / MEDIUM / HIGH)
2. Short explanation
"""

    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )

        return res.json().get("response", "Llama3 error")

    except Exception as e:
        return f"Llama3 failed: {str(e)}"


# =========================
# Risk Gate（是否升级）
# =========================
def should_escalate(signal, llama_text):

    text = llama_text.upper()

    # 高风险 → 升级
    if "HIGH" in text:
        return True

    # 重要交易（方向性强）
    if signal in ["BUY CALL", "BUY PUT", "STRADDLE"]:
        return True

    return False


# =========================
# OpenAI 深度分析
# =========================
def openai_analysis(symbol, market, ind, iv, signal):

    prompt = f"""
You are a professional options strategist.

Analyze this trade deeply:

Symbol: {symbol}
Market: {market}

Price: {ind['price']}
SMA50: {ind['sma50']}
SMA200: {ind['sma200']}
RSI: {ind['rsi']}
IV Rank: {iv}

Signal: {signal}

Provide:
- Detailed reasoning
- Risks
- Suggested improvement
- Confidence (Low/Medium/High)
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-5.3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        return resp.choices[0].message.content

    except Exception as e:
        return f"OpenAI failed: {str(e)}"


# =========================
# 总入口（对外调用这个）
# =========================
def analyze_trade(symbol, market, ind, iv, signal):

    # 第一层：本地 LLM
    llama_text = llama3_analysis(symbol, market, ind, iv, signal)

    # 第二层：是否升级
#    if should_escalate(signal, llama_text):
#        final_text = openai_analysis(symbol, market, ind, iv, signal)
#        source = "OpenAI"
#    else:
    final_text = llama_text
    source = "Llama3"

    return {
        "source": source,
        "analysis": final_text
    }