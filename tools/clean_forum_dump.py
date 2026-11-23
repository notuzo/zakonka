import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Desktop" / "законка блейн 14.11.txt"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SRC.with_name(SRC.stem + ".clean.txt")

ZERO = "\u200b\ufeff\u200e\u200f"
BOUND = re.compile(
    r"^\s*(Последнее редактирование:|Like|Ответить|Поделиться:|Реакции:|"
    r"В этой теме нельзя|Напишите свой ответ)"
)
IMAGE = re.compile(
    r"^\s*(?:\d+\.(?:png|jpe?g|webp|gif)|\*тут\*)\s*$", re.I
)
IMG_TOKEN = re.compile(r"\S*\.(?:png|jpe?g|webp|gif)\b", re.I)
NOISE = re.compile(r"^\s*(?:Спойлер:|Схемы\s*$)")
SEP = re.compile(r"^\s*[=\-_—]{3,}\s*$")


def clean_line(s: str) -> str:
    for ch in ZERO:
        s = s.replace(ch, "")
    return re.sub(r"[ \t]+$", "", s.replace("\xa0", " ")).strip()


def norm_title(s: str) -> str:
    return re.sub(r"[^0-9a-zа-я]+", "", s.lower().replace("ё", "е"))


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    starts = []
    for i in range(2, len(lines)):
        if lines[i].strip().startswith("Автор темы") and lines[i - 2].strip() == "notuzo":
            title = lines[i - 1].strip()
            if title.startswith("Важно "):
                title = title[6:].strip()
            starts.append((i - 1, title))

    docs = []
    for n, (pos, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        posts = [
            j
            for j in range(pos, end)
            if re.fullmatch(r"#\d+", lines[j].strip())
        ]
        if not posts:
            posts = [
                next(
                    (j for j in range(pos, end) if lines[j].strip() == "Добавить закладку"),
                    pos,
                )
            ]
        parts = []
        for pi, h in enumerate(posts):
            meta = "\n".join(lines[max(pos, h - 12) : h])
            if h != posts[0] and "Автор темы" not in meta:
                continue
            body = []
            for j in range(h + 1, end):
                raw = lines[j]
                if BOUND.match(raw):
                    break
                s = clean_line(raw)
                if not s or IMAGE.match(s) or NOISE.match(s) or SEP.match(s):
                    continue
                s = IMG_TOKEN.sub("", s).strip()
                if not s:
                    continue
                if not body and norm_title(s) == norm_title(title):
                    continue
                body.append(s)
            if body:
                parts.append("\n".join(body))
        text = "\n\n".join(parts)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) < 300 and "ДАННОМ ОФИЦИАЛЬНОМ РАЗДЕЛЕ" in text:
            continue
        docs.append({"title": title, "text": text})

    unique = {}
    for d in docs:
        key = norm_title(d["title"])
        if key not in unique or len(d["text"]) > len(unique[key]["text"]):
            unique[key] = d
    docs = list(unique.values())

    laws = [d for d in docs if re.search(r"кодекс|закон|конституц|прецедент", d["title"], re.I)]
    other = [d for d in docs if d not in laws]

    out = [
        "ЗАКОНОДАТЕЛЬНАЯ БАЗА И ДОКУМЕНТЫ ГОСУДАРСТВЕННЫХ ФРАКЦИЙ",
        "GTA5RP, сервер Blaine, штат Сан-Андреас",
        "Выгрузка с forum.gta5rp.com, 14 ноября 2026 года",
        f"Документов: {len(docs)} (законов — {len(laws)}, прочих — {len(other)})",
        "",
        "СОДЕРЖАНИЕ",
        "",
        f"ЧАСТЬ I. ЗАКОНЫ ({len(laws)})",
    ]
    for i, d in enumerate(laws, 1):
        out.append(f"  {i:>2}. {d['title']}")
    out += ["", f"ЧАСТЬ II. ДОКУМЕНТЫ ({len(other)})"]
    for i, d in enumerate(other, 1):
        out.append(f"  {i:>2}. {d['title']}")
    out += ["", "=" * 80, "ЧАСТЬ I. ЗАКОНЫ", "=" * 80, ""]
    for i, d in enumerate(laws, 1):
        out += [f"[{i}/{len(laws)}] {d['title']}", "-" * 80, d["text"], ""]
    out += ["", "=" * 80, "ЧАСТЬ II. ДОКУМЕНТЫ", "=" * 80, ""]
    for i, d in enumerate(other, 1):
        out += [f"[{i}/{len(other)}] {d['title']}", "-" * 80, d["text"], ""]

    OUT.write_text(re.sub(r"\n{4,}", "\n\n\n", "\n".join(out)).strip() + "\n", encoding="utf-8")
    print(f"docs={len(docs)} laws={len(laws)} other={len(other)} out={OUT}")
    for d in docs:
        print(f"  {len(d['text']):6}  {d['title'][:90]}")


if __name__ == "__main__":
    main()
