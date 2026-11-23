import time

import requests

import ask

q = "не пускают к задержанному"
hits = ask.search(q, 10)
env = ask.load_env()
base = env["LLM_BASE"].rstrip("/")
key = env["LLM_API_KEY"]

models = [
    "deepseek/deepseek-v4-flash-0731",
    "openai/gpt-6-luna",
    "xiaomi/mimo-v2.5",
    "qwen3.8-flash",
]

for m in models:
    t = time.perf_counter()
    try:
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": m,
                "messages": [
                    {"role": "system", "content": ask.SYS},
                    {"role": "user", "content": ask.build_user(q, hits)},
                ],
                "temperature": 0.2,
                "max_tokens": 280,
            },
            timeout=60,
        )
        dt = time.perf_counter() - t
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            print(f"{m}: {dt:.2f}s, {len(c)} chars")
            print("  " + c[:180].replace("\n", " "))
        else:
            print(f"{m}: {dt:.2f}s, HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        print(f"{m}: ERR {e}")
