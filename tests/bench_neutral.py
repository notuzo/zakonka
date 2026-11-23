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

data = requests.get(base + "/models", headers=headers, timeout=30).json()["data"]
models = []
for m in data:
    arch = m.get("architecture") or {}
    if "text" not in (arch.get("output_modalities") or []):
        continue
    p = m.get("pricing") or {}
    pr, co = p.get("prompt"), p.get("completion")
    if pr in (None, "") or co in (None, ""):
        continue
    models.append(
        {
            "id": m["id"],
            "prompt_price": float(pr),
            "completion_price": float(co),
            "ctx": m.get("context_length") or 0,
        }
    )
models.sort(key=lambda x: (x["prompt_price"], x["completion_price"], x["id"]))

start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end = int(sys.argv[2]) if len(sys.argv) > 2 else len(models)
out_path = Path(__file__).resolve().parent / "bench_neutral.jsonl"
prompt = "Ответь ровно одним словом: ок"

session = requests.Session()
rows = []
with out_path.open("a", encoding="utf-8") as f:
    for i in range(start, min(end, len(models))):
        m = models[i]
        t0 = time.perf_counter()
        err = None
        content = ""
        finish = None
        try:
            r = session.post(
                base + "/chat/completions",
                headers=headers,
                json={
                    "model": m["id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=25,
            )
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                choice = r.json()["choices"][0]
                content = (choice.get("message", {}).get("content") or "").strip()
                finish = choice.get("finish_reason")
            else:
                err = f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            dt = time.perf_counter() - t0
            err = f"ERR {type(e).__name__}: {str(e)[:100]}"
        row = {
            "n": i + 1,
            "model": m["id"],
            "prompt_price": m["prompt_price"],
            "completion_price": m["completion_price"],
            "ctx": m["ctx"],
            "time": round(dt, 2),
            "content": content,
            "finish": finish,
            "error": err,
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        rows.append(row)
        print(f'{i+1}/{len(models)} {dt:6.2f}s {m["id"]}: {content!r} {finish or err or ""}')

print("\n--- итог батча ---")
for r in sorted(rows, key=lambda x: x["time"]):
    print(f'{r["time"]:6.2f}s  {r["model"]}  {r["content"]!r}')
