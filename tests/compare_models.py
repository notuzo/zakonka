import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

import ask

sys.stdout.reconfigure(encoding="utf-8")

env = ask.load_env()
base = env["LLM_BASE"].rstrip("/")
key = env["LLM_API_KEY"]
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

q = "не пускают к задержанному"
hits = ask.search(q, 6)
user = ask.build_user(q, hits)
models = [
    "openai/gpt-6-luna",
    "openai/gpt-5.6-terra",
    "z-ai/glm-5.2",
    "deepseek/deepseek-v4.1-flash-1017",
    "qwen/qwen3.8-flash",
    "xiaomi/mimo-v2.5",
]

for m in models:
    t0 = time.perf_counter()
    try:
        r = requests.post(
            base + "/chat/completions",
            headers=headers,
            json={
                "model": m,
                "messages": [
                    {"role": "system", "content": ask.SYS},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 160,
            },
            timeout=30,
        )
        dt = time.perf_counter() - t0
        if r.status_code == 200:
            c = (r.json()["choices"][0]["message"].get("content") or "").strip()
            warn = ask.check_phrase(c)
            print(f"\n=== {m} | {dt:.2f}s | {len(c)} chars ===")
            print(c[:500])
            if warn:
                print("WARN:", "; ".join(warn))
        else:
            print(f"\n=== {m} | {dt:.2f}s | HTTP {r.status_code} ===")
            print(r.text[:200])
    except Exception as e:
        print(f"\n=== {m} | ERR {type(e).__name__}: {str(e)[:120]} ===")
