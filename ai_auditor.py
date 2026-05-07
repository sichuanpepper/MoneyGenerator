import os
import requests
import google.generativeai as genai
from openai import OpenAI
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class AIAuditor:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            # 使用你列表中存在的最新稳定版模型
            try:
                # 推荐使用 2.5-flash，速度快且审计能力强
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                print("✅ Gemini 2.5 Flash 加载成功")
            except Exception as e:
                # 备选方案：使用 flash-latest 别名
                self.gemini_model = genai.GenerativeModel('gemini-flash-latest')
                print(f"⚠️ 切换至备选模型: {e}")
        else:
            self.gemini_model = None
            print("❌ 未检测到 GEMINI_API_KEY")

     # --- OpenAI 初始化 ---
        api_key_openai = os.getenv("OPENAI_API_KEY")
        if api_key_openai:
            try:
                # 默认使用最新的 gpt-4o-mini，性价比最高且速度快
                self.openai_client = OpenAI(api_key=api_key_openai)
                print("✅ OpenAI Client (GPT-4o) 加载成功")
            except Exception as e:
                self.openai_client = None
                print(f"❌ OpenAI 加载失败: {e}")
        else:
            self.openai_client = None
            print("⚠️ 未检测到 OPENAI_API_KEY")       

    # --- Claude (新增) ---
        api_key_anthropic = os.getenv("ANTHROPIC_API_KEY")
        if api_key_anthropic:
            try:
                self.claude_client = Anthropic(api_key=api_key_anthropic)
                print("✅ Claude Client (Claude 3.5 Sonnet) 加载成功")
            except Exception as e:
                self.claude_client = None
                print(f"❌ Claude 加载失败: {self._clean_err(e)}")
        else:
            self.claude_client = None   
            print("⚠️ 未检测到 ANTHROPIC_API_KEY")   

    def _clean_err(self, e):
        """异常消息截断处理"""
        err_str = str(e).replace('\n', ' ')
        return (err_str[:297] + "...") if len(err_str) > 100 else err_str          

    def call_llama3(self, prompt, max_tokens=2000):
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 5000}
                },
                timeout=15
            )
            return res.json().get("response", "N/A")
        except Exception as e:
            return f"Llama3 Error: {self._clean_err(e)}"     

    def audit(self, engine, mode, data):
        # --- 关键修改：缩短 max_tokens 以强制精简输出 ---
        max_tokens = 2000 
        
        if mode == 'stock':
            prompt = self._stock_prompt(data)
        elif mode == 'sentinel':
            prompt = self._sentinel_prompt(data)
        # --- 修复点：添加对 options 模式的处理 ---
        elif mode == 'options':
            prompt = self._options_prompt(data)
        else:
            prompt = f"Summarize these financial data points concisely: {str(data)}"

        if engine == 'gemini':
            if not self.gemini_model: return "Gemini not configured."
            try:
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": max_tokens, "temperature": 0.2}
                )
                return response.text.strip()
            except Exception as e:
                return f"Gemini Error: {self._clean_err(e)}"
        elif engine == 'openai':
            if not self.openai_client: return "OpenAI not configured."
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini", # 或者使用 "gpt-4o"
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.2
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                return f"OpenAI Error: {self._clean_err(e)}"  
        elif engine == 'claude':
            if not self.claude_client: return "Claude not configured."
            try:
                # Claude 调用语法与 OpenAI 略有不同
                response = self.claude_client.messages.create(
                    model="claude-sonnet-4-6", # 推荐用 3.5 Sonnet，审计能力最强
                    max_tokens=max_tokens,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}]
                )
                # Claude 返回的是 Content Block 列表
                return response.content[0].text.strip()
            except Exception as e:
                return f"Claude Error: {self._clean_err(e)}"        

        
        return self.call_llama3(prompt, max_tokens)

    def _stock_prompt(self, d):
        return f"""
        [Role: Senior Quantitative Trader]
        Task: Audit the following trade signal.
        
        Data:
        - Symbol: {d['symbol']} | Market: {d['market']}
        - Signal: {d['final_signal']}
        - RSI: {d['rsi']} | Vol Ratio: {d['vol_ratio']}x
        - Reasons: {', '.join(d['reasons'])}
        
        Requirements (Strict Output Format):
        1. [Result]: (Strongly Disagree / Disagree / Neutral / Agree / Strongly Agree)
        2. [Action]: (Strong Buy 🟢 / Buy / Hold 🟡 / Weak Sell / Sell 🔴)
        3. [Reason]: Two or three concise sentences focusing on why and risk or validation.
        """

    def _options_prompt(self, d):
        # 针对期权策略（如 Call Spread, Long Call 等）的特定审计逻辑
        return f"""
        [Role: Derivatives Risk Manager]
        Task: Audit the following Options Trade.
        
        Data:
        - Symbol: {d['symbol']} | Strategy: {d['strategy']}
        - Underlying Price: ${d['underlying_price']}
        - Strike: {d['strike']} | Expiry: {d['expiry']}
        - Market Context: {d['market']}
        - Technical Context: RSI={d['rsi']}, Vol={d['vol_ratio']}x
        
        Requirements:
        Requirements (Strict Output Format):
        1. [Result]: (High Confidence/ Reasonable / Speculative / High Risk )
        2. [Action]: (Strong Buy 🟢 / Buy / Hold 🟡 / Avoid ❌ / EXIT 🚨 / Take Profit 💰)
        3. [Reason]: Two or three concise sentences focusing on why and IV/Theta. Prioritize checking if the 'time to expiry' and 'volatility' justify the strategy.
        """

    def _sentinel_prompt(self, d):
        return f"""
        [Role: Risk Management Director]
        Task: Emergency exit audit for {d['symbol']}.
        
        Context:
        - Trigger: {d['alert_type']}
        - Profit/Loss: {d['ret']:.1%} | Drawdown from Peak: {d['drawdown']:.1%}
        - Current Price: ${d['price']}
        
        Requirements:
        1. Start with ONE action tag: [EXERT EXIT] | [REDUCE POSITION] | [HOLD] | [IGNORE]
        2. Follow with ONE sharp justification. Focus on whether this is a 'normal pullback' or 'trend reversal'.
        3. Be extremely concise. No fluff.
        """