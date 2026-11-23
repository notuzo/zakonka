import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ask

sys.stdout.reconfigure(encoding="utf-8")

QUESTIONS = [
    "не пускают к задержанному",
    "коп хочет обыскать машину без ордера",
    "задержали без объяснения причины",
    "допрашивают без разъяснения прав",
    "сколько могут держать задержанного",
    "хотят обыскать квартиру",
    "применили силу или оружие",
    "хотят прочитать переписку или забрать телефон",
    "задержали государственного служащего",
    "как обжаловать действия сотрудника",
    "не дают позвонить по телефону",
    "задержали несовершеннолетнего",
]

out_dir = Path(__file__).resolve().parent
jsonl = out_dir / "results.jsonl"
txt = out_dir / "results.txt"
rows = []
with jsonl.open("w", encoding="utf-8") as jf, txt.open("w", encoding="utf-8") as tf:
    for i, q in enumerate(QUESTIONS, 1):
        t0 = time.perf_counter()
        hits = ask.search(q, 6)
        phrase, err = ask.call_llm(q, hits[:6])
        dt = time.perf_counter() - t0
        warnings = ask.check_phrase(phrase) if phrase else []
        top = [f'{a["doc_short"]} ст. {a["article"]}' for a in hits[:6]]
        row = {
            "n": i,
            "q": q,
            "time": round(dt, 2),
            "top": top,
            "phrase": phrase,
            "error": err,
            "warnings": warnings,
        }
        rows.append(row)
        jf.write(json.dumps(row, ensure_ascii=False) + "\n")
        tf.write(f"\n=== {i}. {q} | {dt:.2f}s ===\n")
        tf.write("TOP: " + ", ".join(top) + "\n")
        if err:
            tf.write("ERROR: " + err + "\n")
        else:
            tf.write("PHRASE: " + phrase + "\n")
        if warnings:
            tf.write("WARN: " + "; ".join(warnings) + "\n")
        print(f'{i}/{len(QUESTIONS)} {dt:.2f}s {q}')

print(f"\nresults: {txt}")
print(f"jsonl: {jsonl}")
