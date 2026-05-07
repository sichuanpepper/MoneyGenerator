import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
print("API KEY:", api_key)  # 确认不是 None

client = anthropic.Anthropic(api_key=api_key)

try:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=50,
        messages=[
            {"role": "user", "content": "Say hello briefly."}
        ]
    )
    print("✅ Success:", response.content[0].text)
except Exception as e:
    print("❌ Error:", e)