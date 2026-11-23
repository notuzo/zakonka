import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "corpus" / "gta5rp-vse-dokumenty.txt"
OUT = ROOT / "corpus" / "parts"
INDEX = ROOT / "corpus" / "INDEX.tsv"

lines = SRC.read_text(encoding="utf-8").splitlines()
cut = next(
    (
        i
        for i, l in enumerate(lines)
        if l.startswith("ЧАСТЬ II.") and i and lines[i - 1].startswith("=")
    ),
    None,
)
if cut is None:
    raise SystemExit("нет заголовка ЧАСТЬ II.")

OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.txt"):
    old.unlink()

(OUT / "01-zakony.txt").write_text("\n".join(lines[:cut]).strip() + "\n", encoding="utf-8")
(OUT / "02-dokumenty.txt").write_text("\n".join(lines[cut:]).strip() + "\n", encoding="utf-8")

rows = ["doc\tpart\ttitle\tfile"]
DOC_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*(.*)$")
for i, line in enumerate(lines):
    m = DOC_RE.match(line)
    if not m:
        continue
    num, total, title = m.groups()
    fname = "01-zakony.txt" if i < cut else "02-dokumenty.txt"
    rows.append(f"{num}/{total}\t{total}\t{title}\t{fname}")
INDEX.write_text("\n".join(rows) + "\n", encoding="utf-8")

print("parts:", len(list(OUT.glob("*.txt"))), "docs:", len(rows) - 1, "index:", INDEX)
