import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = "openchat/openchat-3.5"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/116.0.5845.188 Safari/537.36"
}

data = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2 + 2?"}
    ],
    "temperature": 0,
    "max_tokens": 10
}

try:
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=30
    )
    print("Status:", response.status_code)
    print("Response:", response.json())
except Exception as e:
    print("Error:", str(e))
