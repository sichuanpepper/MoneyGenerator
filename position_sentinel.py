import yfinance as yf
import json
import os
import time
import requests
import pytz
from datetime import datetime
from dotenv import load_dotenv

# =========================
# 配置与初始化
# =========================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_ALERTS")
POSITIONS_FILE = "positions.json"
SENTINEL_STATE = "sentinel_state.json"
EASTERN = pytz.timezone("US/Eastern")

# =========================
# 核心逻辑
# =========================
def load_json(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def send_slack(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending Slack notify...")
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
        except:
            print("Failed to send Slack notification.")

# =========================
# 心跳与 Greeting 逻辑
# =========================
def send_morning_greeting(positions, state):
    """每天开盘前发送持仓简报"""
    now_et = datetime.now(EASTERN)
    # 检查是否为工作日 (0-4 是周一到周五)
    if now_et.weekday() > 4:
        return

    summary = []
    for s, info in positions.items():
        hw = state.get(s, {}).get("high_watermark", "N/A")
        summary.append(f"• *{s}*: Entry ${info['entry_price']} | Peak ${hw}")

    pos_str = "\n".join(summary) if summary else "No active positions."
    
    greeting_msg = f"""
☀️ *Good Morning! Market Sentinel is Online.*
⏰ Time: {now_et.strftime('%Y-%m-%d %H:%M')} ET
📈 *Current Portfolio Overview:*
{pos_str}

🚀 _System is ready. Monitoring minute-by-minute..._
"""
    send_slack(greeting_msg)

# =========================
# 主程序
# =========================
def run_sentinel():
    print("🚨 POSITION SENTINEL V1.1 (WITH HEARTBEAT) STARTED")
    state = load_json(SENTINEL_STATE)
    last_heartbeat_date = state.get("last_heartbeat_date", "")

    while True:
        try:
            now_et = datetime.now(EASTERN)
            positions = load_json(POSITIONS_FILE)
            
            # --- 心跳检查逻辑 (每天 09:25 ET 发送一次) ---
            current_date_str = now_et.strftime("%Y-%m-%d")
            if now_et.hour == 9 and now_et.minute == 25 and last_heartbeat_date != current_date_str:
                send_morning_greeting(positions, state)
                last_heartbeat_date = current_date_str
                state["last_heartbeat_date"] = current_date_str
                save_json(SENTINEL_STATE, state)

            if not positions:
                time.sleep(60)
                continue

            # --- 核心监控逻辑 ---
            for s, info in positions.items():
                df = yf.download(s, period="2d", interval="1m", progress=False)
                if df.empty: continue
                
                curr_p = round(float(df["Close"].iloc[-1]), 2)
                entry_p = info["entry_price"]
                
                # 更新最高价状态
                if s not in state or isinstance(state[s], str): # 容错处理
                    state[s] = {"high_watermark": curr_p, "last_alert": None}
                
                if curr_p > state[s].get("high_watermark", 0):
                    state[s]["high_watermark"] = curr_p
                
                hw = state[s]["high_watermark"]
                drawdown = (curr_p - hw) / hw
                total_ret = (curr_p - entry_p) / entry_p
                
                alert_type = None
                if total_ret < -0.07:
                    alert_type = "🚨 HARD STOP-LOSS"
                elif total_ret > 0.10 and drawdown < -0.05:
                    alert_type = "💰 TRAILING TAKE-PROFIT"

                if alert_type and state[s].get("last_alert") != alert_type:
                    # 此处可插入之前写的 llama3_risk_audit 逻辑
                    msg = f"⚠️ *{alert_type} TRIGGERED*\nStock: {s}\nPrice: ${curr_p}\nReturn: {total_ret:.1%}\nDrawdown: {drawdown:.1%}"
                    send_slack(msg)
                    state[s]["last_alert"] = alert_type

            save_json(SENTINEL_STATE, state)
            
            # 根据开盘时间动态调整睡眠频率
            # 开盘时间 (9:30-16:00) 1分钟扫一次，其余时间 10分钟扫一次
            if 9 <= now_et.hour <= 16:
                time.sleep(180)
            else:
                time.sleep(3600) 
                
        except Exception as e:
            print(f"Sentinel Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_sentinel()