"""快速 ping 4 个模型，确认能调通再批量跑评测。"""
import os
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from langchain_openai import ChatOpenAI

MODELS = ["glm-5.2", "minimax-m3", "kimi-k2.6", "deepseek-v4-pro"]
BASE_URL = os.getenv("CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
API_KEY = os.getenv("CHAT_API_KEY", "")

async def ping(model: str):
    c = ChatOpenAI(
        openai_api_base=BASE_URL,
        openai_api_key=API_KEY,
        model=model,
        temperature=0,
        max_tokens=20,
        timeout=30,
    )
    try:
        r = await c.ainvoke("say 'ok' in english, one word.")
        return model, "OK", str(r.content)[:50]
    except Exception as e:
        return model, "ERR", str(e)[:200]

async def main():
    print(f"base_url={BASE_URL}")
    print(f"key={'set' if API_KEY else 'MISSING'}")
    results = await asyncio.gather(*[ping(m) for m in MODELS])
    for m, status, msg in results:
        print(f"  [{status}] {m:25s} {msg}")

asyncio.run(main())
