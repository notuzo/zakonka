import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

import ask

sys.stdout.reconfigure(encoding="utf-8")

env = ask.load_env()
base = env["LLM_BASE"].rstrip("/")
key = env["LLM_API_KEY"]
data = requests.get(base + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30).json()["data"]

priced = []
unpriced = []
for m in data:
    p = m.get("pricing") or {}
    pr, co = p.get("prompt"), p.get("completion")
    mods = (m.get("architecture") or {}).get("input_modalities") or []
    mod = "+".join(mods) if mods else "?"
    ctx = m.get("context_length") or 0
    if pr not in (None, "") and co not in (None, ""):
        priced.append((float(pr), float(co), m["id"], ctx, mod))
    else:
        unpriced.append((m["id"], ctx, mod))

priced.sort(key=lambda x: (x[0], x[1], x[2]))
unpriced.sort(key=lambda x: x[0])


def ctxs(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{n//1000}k"
    return str(n)


out = []
out.append(f"ВСЕГО: {len(data)} | с ценой: {len(priced)} | без цены: {len(unpriced)}")
out.append("ЦЕНЫ: $ за 1M токенов (prompt / completion), сортировка по prompt")
out.append("")
out.append(f'{"#":>3}  {"модель":<46} {"prompt":>9} {"compl":>9} {"ctx":>7}  модальность')
out.append("-" * 100)
for i, (pr, co, mid, ctx, mod) in enumerate(priced, 1):
    out.append(f"{i:>3}. {mid:<46} {pr:>9.6g} {co:>9.6g} {ctxs(ctx):>7}  {mod}")
out.append("")
out.append("БЕЗ ЦЕНЫ (в основном медиа):")
out.append(f'{"модель":<50} {"ctx":>7}  модальность')
out.append("-" * 80)
for mid, ctx, mod in unpriced:
    out.append(f"{mid:<50} {ctxs(ctx):>7}  {mod}")

path = Path(__file__).resolve().parents[1] / "models_prices.txt"
path.write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
print(f"\nсохранено: {path}")
