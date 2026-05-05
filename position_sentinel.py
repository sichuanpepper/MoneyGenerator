import yfinance as yf
import json
import os
import time
import requests
import pytz
from datetime import datetime
from dotenv import load_dotenv
from ai_auditor import AIAuditor 

# ==========================================
# 1. 初始化
# ==========================================
load_dotenv()
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_ALERTS")
POSITIONS_FILE = "positions.json"
SENTINEL_STATE = "sentinel_state.json"
EASTERN = pytz.timezone("US/Eastern")

auditor = AIAuditor()

# ==========================================
# 2. 通讯与工具
# ==========================================
def send_slack(msg):
    if WEBHOOK_URL:
        try: 
            # 增加打印方便本地调试
            print(f"尝试发送 Slack: {msg[:30]}...") 
            res = requests.post(WEBHOOK_URL, json={"text": msg}, timeout=5)
            if res.status_code != 200:
                print(f"Slack 返回错误码: {res.status_code}")
        except Exception as e: 
            print(f"Slack 发送失败异常: {e}")
    else:
        print("警告: 未配置 SLACK_WEBHOOK_ALERTS")

def load_json(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

# ==========================================
# 3. 主哨兵逻辑
# ==========================================
def run_sentinel():
    # --- 修复点 1: 启动消息发送 ---
    start_msg = "🚀 哨兵系统 V1.6 (Hybrid AI) 启动..."
    print(start_msg)
    send_slack(start_msg) # 显式调用发送函数
    
    state = load_json(SENTINEL_STATE)
    
    while True:
        try:
            now_et = datetime.now(EASTERN)
            positions = load_json(POSITIONS_FILE)
            
            for s, info in positions.items():
                # 下载最近 2 天数据
                df = yf.download(s, period="2d", interval="1m", progress=False)
                if df.empty: continue
                
                # --- 修复点 2: 消除 FutureWarning ---
                # 使用 .values[-1] 获取纯 NumPy 数值，彻底避开 Series 转换警告
                raw_close = df["Close"].values[-1]
                curr_p = round(float(raw_close), 2)
                
                entry_p = info["entry_price"]
                
                # 状态维护
                if s not in state: state[s] = {"high_watermark": curr_p, "last_alert": None}
                
                # 确保 high_watermark 存在且为有效数字
                if curr_p > state[s].get("high_watermark", 0):
                    state[s]["high_watermark"] = curr_p
                    state[s]["last_alert"] = None
                
                hw = state[s]["high_watermark"]
                total_ret = (curr_p - entry_p) / entry_p
                drawdown = (curr_p - hw) / hw
                
                # 预警逻辑
                alert_type = None
                if total_ret < -0.07: 
                    alert_type = "🚨 硬止损 (Entry -7%)"
                elif total_ret > 0.10 and drawdown < -0.05: 
                    alert_type = "💰 移动止盈 (Peak -5%)"

                # 触发审计
                if alert_type and state[s].get("last_alert") != alert_type:
                    audit_payload = {
                        "symbol": s,
                        "alert_type": alert_type,
                        "price": curr_p,
                        "ret": total_ret,
                        "drawdown": drawdown
                    }
                    
                    print(f"🤖 正在请求双 AI 审计 {s}...")
                    llama_opinion = auditor.audit('llama3', 'sentinel', audit_payload)
                    gemini_opinion = auditor.audit('gemini', 'sentinel', audit_payload)
                    
                    msg = f"""
⚠️ *{alert_type}*
*股票*: {s} | *现价*: ${curr_p}
*盈亏*: {total_ret:+.1%} | *回撤*: {drawdown:.1%}

---
🤖 *Llama3 (Local)*: 
{llama_opinion}

🌟 *Gemini (Cloud)*: 
{gemini_opinion}
"""
                    send_slack(msg)
                    state[s]["last_alert"] = alert_type

            save_json(SENTINEL_STATE, state)
            
            # 自动调整频率
            sleep_time = 60 if 9 <= now_et.hour <= 16 else 600
            time.sleep(sleep_time)

        except Exception as e:
            print(f"运行异常: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_sentinel()