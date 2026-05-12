import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv
import pandas as pd
from ai_auditor import AIAuditor  # 确保此文件在同一目录下

# =========================
# 1. 初始化配置
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_STOCK")
STATE_FILE = "stock_state.json"
WATCHLIST_FILE = "watchlist_stock.json"
EASTERN = pytz.timezone("US/Eastern")

auditor = AIAuditor()

# =========================
# 2. 工具函数
# =========================
def send_slack(msg):
    if WEBHOOK_URL:
        try:
            print(f"📡 Sending Slack Alert...")
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
        except:
            print("❌ Slack notify error")

def load_json(path, key=None):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return data.get(key, []) if key else data
        except: return [] if key else {}
    return [] if key else {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def fmt(x, d=2):
    """消除 FutureWarning 的数值转换"""
    if hasattr(x, "values"):
        val = x.values[-1] if len(x) > 0 else 0
    elif hasattr(x, "iloc"):
        val = x.iloc[-1]
    else:
        val = x
    return round(float(val), d)

# =========================
# 3. 核心指标计算 (修复缺失定义)
# =========================
def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

def get_market():
    """判断大盘趋势 (SPY)"""
    data = yf.download("SPY", period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "UNKNOWN"
    
    close = data["Close"].squeeze()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    
    p = fmt(close)
    s50 = fmt(sma50)
    s200 = fmt(sma200)
    ps200 = fmt(sma200.shift(1)) # 前一天的 SMA200

    if p > s200 and s50 > s200 and s200 > ps200: return "BULL"
    if p < s200 and s50 < s200: return "BEAR"
    return "NEUTRAL"

# =========================
# 4. 策略逻辑
# =========================
def long_term(symbol):
    data = yf.download(symbol, period="1y", interval="1d", progress=False)
    if data.empty or len(data) < 200: return "NEUTRAL", {}

    close = data["Close"].squeeze()
    s50 = close.rolling(50).mean()
    s200 = close.rolling(200).mean()

    p, v50, v200 = fmt(close), fmt(s50), fmt(s200)
    sig = "BULLISH" if p > v200 and v50 > v200 else ("BEARISH" if p < v200 else "NEUTRAL")
    return sig, {"price": p, "sma50": v50, "sma200": v200, "signal": sig}

def short_term(symbol):
    data = yf.download(symbol, period="5d", interval="5m", progress=False)
    if data.empty: return "HOLD", {}

    close = data["Close"].squeeze()
    volume = data["Volume"].squeeze()
    
    m20 = close.rolling(20).mean()
    m50 = close.rolling(50).mean()
    r_val = rsi_calc(close)
    
    # 成交量计算
    curr_vol = float(volume.values[-1])
    avg_vol = float(volume.iloc[-21:-1].mean())
    vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    p, v20, v50, rv = fmt(close), fmt(m20), fmt(m50), fmt(r_val, 1)

    score = 0
    reasons = []
    if v20 > v50: score += 1; reasons.append("MA20 > MA50")
    else: score -= 1; reasons.append("MA20 < MA50")
    
    if p > v20: score += 1; reasons.append("Price > MA20")
    else: score -= 1; reasons.append("Price < MA20")

    if rv < 35: score += 1; reasons.append("RSI Oversold")
    elif rv > 70: score -= 2; reasons.append("RSI Overbought")
    
    if vol_ratio > 2.0: reasons.append(f"Volume Surge ({vol_ratio}x)")

    ind = {"price": p, "ma20": v20, "ma50": v50, "rsi": rv, "vol_ratio": vol_ratio, "reasons": reasons}
    sig = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")
    return sig, ind

def fuse(short, long, market):
    if market == "BEAR":
        return "STRONG SELL" if short == "SELL" else ("BLOCKED BUY" if short == "BUY" else "HOLD")
    if market == "NEUTRAL":
        return "WEAK BUY" if (short == "BUY" and long == "BULLISH") else ("SELL" if short == "SELL" else "HOLD")
    if market == "BULL":
        return "STRONG BUY" if (short == "BUY" and long == "BULLISH") else ("WEAK SELL" if short == "SELL" else "HOLD")
    return "HOLD"

def position(signal, market):
    maps = {
        "BULL": {"STRONG BUY": 80, "WEAK BUY": 60, "HOLD": 40, "WEAK SELL": 20},
        "BEAR": {"STRONG SELL": 0, "SELL": 10, "HOLD": 20, "BLOCKED BUY": 10}
    }
    return maps.get(market, {"BUY": 40, "HOLD": 30, "SELL": 20}).get(signal, 30)

def extract_audit_result(text):
    """从 AI 回复中提取标准化结果"""
    text = text.upper()
    if "STRONGLY AGREE" in text or "AGREE" in text:
        return "AGREE"
    if "STRONGLY DISAGREE" in text or "DISAGREE" in text:
        return "DISAGREE"
    return "NEUTRAL"    

# =========================
# 5. 主循环
# =========================
def run():
    state = load_json(STATE_FILE)
    start_msg = "🚀 STOCK MONITOR V3.4 (CASCADE AUDIT ENABLED) STARTED"
    print(start_msg)
    send_slack(start_msg)

    while True:
        try:
            symbols = load_json(WATCHLIST_FILE, key="symbols")
            market = get_market()
            now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S ET")

            for s in symbols:
                short_sig, short_ind = short_term(s)
                long_sig, long_ind = long_term(s)
                if not short_ind or not long_ind:
                    continue

                final_prog = fuse(short_sig, long_sig, market)
                pos = position(final_prog, market)
                prev = state.get(s, {})
                prev_signal = prev.get("signal")

                audit_payload = {
                    "symbol": s, "market": market, "final_signal": final_prog,
                    "rsi": short_ind.get('rsi'), "vol_ratio": short_ind.get('vol_ratio'),
                    "reasons": short_ind.get('reasons'), "long_sig": long_sig
                }

                # ── 第一层：Llama3 本地审计 ──────────────────────────────────
                llama_res = auditor.audit('llama3', 'stock', audit_payload)
                l_status = extract_audit_result(llama_res)
                llama_agree = (l_status == "AGREE")

                # 条件：Llama3 同意 且 signal 未变 → 跳过
                if llama_agree and (final_prog == prev_signal):
                    print(f"✅ {s}: Llama3 agrees & signal unchanged, skipping.")
                    continue

                # ── 第二层：Cloud 审计（Gemini + OpenAI）────────────────────
                print(f"☁️  {s}: Proceeding to cloud audit (Gemini & OpenAI)...")
                gemini_res = auditor.audit('gemini', 'stock', audit_payload)
                openai_res = auditor.audit('openai', 'stock', audit_payload)

                g_status = extract_audit_result(gemini_res)
                o_status = extract_audit_result(openai_res)

                gemini_agree  = (g_status == "AGREE")
                openai_agree  = (o_status == "AGREE")

                if g_status == o_status:
                    # Gemini 与 OpenAI 一致 → 直接采纳
                    final_decision_signal = final_prog if gemini_agree else prev_signal
                    decision_source = "Cloud Consensus (Gemini + OpenAI)"
                    supporters = "🌟 Gemini + 🧠 OpenAI"

                    vol_icon = "🔥" if short_ind['vol_ratio'] > 2.0 else ""
                    msg = f"""
📊 *{s}* {vol_icon} | Logic: {decision_source}
🌎 Market: {market} | ⏰ {now}

👉 TARGET: *{final_decision_signal}* (Prog: {final_prog})
🤝 Supported by: {supporters}

🤖 *Llama3*: {llama_res}
🌟 *Gemini*: {gemini_res}
🧠 *OpenAI*: {openai_res}
"""
                    send_slack(msg)
                    state[s] = {"signal": final_decision_signal, "position": pos}
                    save_json(STATE_FILE, state)
                    continue

                # ── 第三层：终极仲裁（Claude）────────────────────────────────
                print(f"⚖️  {s}: Gemini/OpenAI conflict, calling Claude for arbitration...")
                claude_res = auditor.audit('claude', 'stock', audit_payload)
                c_status = extract_audit_result(claude_res)
                claude_agree = (c_status == "AGREE")

                # Claude 结论永远为准，确定最终 signal
                final_decision_signal = final_prog if claude_agree else prev_signal

                # 统计哪些 AI 与 Claude 一致，用于 Slack 标注
                supporters_list = ["❄️ Claude"]
                if c_status == g_status:
                    supporters_list.append("🌟 Gemini")
                if c_status == o_status:
                    supporters_list.append("🧠 OpenAI")

                supporters = " + ".join(supporters_list)
                if len(supporters_list) == 1:
                    decision_source = "Claude Arbitration (sole)"
                else:
                    decision_source = f"Claude Arbitration ({' + '.join(supporters_list[1:])} aligned)"

                vol_icon = "🔥" if short_ind['vol_ratio'] > 2.0 else ""
                msg = f"""
📊 *{s}* {vol_icon} | Logic: {decision_source}
🌎 Market: {market} | ⏰ {now}

👉 TARGET: *{final_decision_signal}* (Prog: {final_prog})
🤝 Supported by: {supporters}

🤖 *Llama3*: {llama_res}
🌟 *Gemini*: {gemini_res}
🧠 *OpenAI*: {openai_res}
❄️ *Claude*: {claude_res}
"""
                send_slack(msg)
                state[s] = {"signal": final_decision_signal, "position": pos}
                save_json(STATE_FILE, state)

            save_json(STATE_FILE, state)
            time.sleep(300)

        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
            time.sleep(60)
            
if __name__ == "__main__":
    run()