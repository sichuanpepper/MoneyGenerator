import os
import requests
import google.generativeai as genai
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

    def call_llama3(self, prompt, max_tokens=2000):
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": max_tokens}
                },
                timeout=15
            )
            return res.json().get("response", "N/A")
        except Exception as e:
            return f"Llama3 Error: {e}"            

    def call_gemini(self, prompt):
        """调用云端 Gemini"""
        if not self.gemini_model:
            return "Gemini API Key not configured."
        try:
            response = self.gemini_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return f"Gemini Error: {str(e)}"

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
                return f"Gemini Error: {e}"
        
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
        
        Requirements:
        1. Start with ONE tag: [Strongly Disagree] | [Disagree] | [Neutral] | [Agree] | [Strongly Agree]
        2. Follow with ONE concise sentence (max 50 words) explaining the primary risk or confirmation.
        3. Do NOT provide bullet points or detailed technical descriptions.
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
        1. Start with ONE tag: [High Confidence] | [Reasonable] | [Speculative] | [High Risk]
        2. Follow with ONE concise sentence (max 50 words). 
        3. Prioritize checking if the 'time to expiry' and 'volatility' justify the strategy.
        4. No boilerplate text.
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