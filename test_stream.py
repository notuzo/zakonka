import json
import time

import requests

import ask

q = "не пускают к задержанному"
hits = ask.search(q, 6)
env = ask.load_env()
base = env["LLM_BASE"].rstrip("/")
key = env["LLM_API_KEY"]
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def stream(model):
    t0 = time.perf_counter()
    r = requests.post(
        base + "/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": ask.SYS},
                {"role": "user", "content": ask.build_user(q, hits)},
            ],
            "temperature": 0.1,
            "max_tokens": 160,
            "stream": True,
        },
        stream=True,
        timeout=90,
    )
    if r.status_code != 200:
        print(f"{model}: HTTP {r.status_code} {r.text[:120]}")
        return
    first = None
    out = []
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except Exception:
            continue
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {}).get("content")
        if delta:
            if first is None:
                first = time.perf_counter() - t0
            out.append(delta)
    total = time.perf_counter() - t0
    text = "".join(out)
    print(f"{model}: TTFT {first if first is None else round(first,2)}s, total {total:.2f}s, {len(text)} chars")
    print("  " + text[:240].replace("\n", " "))


print("prompt chars:", len(ask.build_user(q, hits)) + len(ask.SYS))
for m in ["openai/gpt-6-luna", "xiaomi/mimo-v2.5", "qwen3.8-flash"]:
    stream(m)
