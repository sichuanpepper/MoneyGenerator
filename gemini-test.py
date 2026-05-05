import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

try:
    # 替换为你列表里的确切名称
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("Ping")
    print("✅ 完美连接:", response.text)
except Exception as e:
    print("❌ 错误依然存在:", e)