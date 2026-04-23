#!/usr/bin/env python
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_gemini_api():
    API_KEY = os.getenv("GEMINI_API_KEY")
    MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-1.5-flash")

    if not API_KEY:
        print("❌ Không tìm thấy GEMINI_API_KEY trong .env")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Xin chào, bạn là AI trợ lý y tế"}
                ]
            }
        ]
    }

    print(f"🔄 Testing Gemini API với key: {API_KEY[:20]}...")
    print(f"📡 URL: {url}")

    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            reply = data["candidates"][0]["content"]["parts"][0]["text"]
            print("✅ API HOẠT ĐỘNG!")
            print(f"🤖 Reply: {reply[:200]}...")
            return True
        else:
            print("❌ API LỖI:")
            print(response.text)
            return False

    except Exception as e:
        print(f"❌ Lỗi kết nối: {str(e)}")
        return False

if __name__ == "__main__":
    test_gemini_api()