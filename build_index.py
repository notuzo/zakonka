import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "corpus" / "gta5rp-vse-dokumenty.txt"

DOC_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*(.*)$")
ART_RE = re.compile(r"^Статья\s+([0-9]+(?:\.[0-9]+)*)(?:\.\s*|\s+(?=[А-ЯЁ«\"(]))(.*)$")
NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s*(.*)$")


def short_title(title: str, part: str = "42") -> str:
    t = title.lower().replace("ё", "е")
    if part != "42":
        if "мэрии" in t:
            return "Регламент мэрии"
        if "администрации губернатора" in t:
            return "Администрация губернатора"
        if "national guard" in t or "национальной гвардии" in t:
            return "Устав NG"
        if "lssd" in t:
            return "Устав LSSD"
        if "условно-досрочное" in t:
            return "УДО"
        if "регламент" in t and "los santos police" in t:
            return "Регламент LSPD"
        if "внутренний устав" in t and "los santos police" in t:
            return "Устав LSPD"
        if "emergency medical" in t:
            return "Устав EMS"
        if "fib" in t:
            return "Устав FIB"
        if "устав управления тюрем" in t:
            return "Устав SASPA"
        if "распорядок" in t:
            return "Распорядок SASPA"
        if "федеральной тюрьмы" in t:
            return "Регламент тюрьмы"
        if "акты управления тюрем" in t:
            return "Акты SASPA"
        if "коллегии адвокатов" in t:
            return "Устав КА"
        if "коллегия адвокатов" in t:
            return "Регламент КА"
        return title[:32]
    rules = [
        ("уголовный кодекс", "УК"),
        ("кодекс об административных", "КоАП"),
        ("процессуальный кодекс", "ПК"),
        ("гражданский кодекс", "ГК"),
        ("трудовой кодекс", "ТК"),
        ("дорожный кодекс", "ДК"),
        ("этический кодекс", "ЭК"),
        ("воздушный кодекс", "ВК"),
        ("конституция", "Конституция"),
        ("об адвокатуре", "Адвокатура"),
        ("о правительстве", "Правительство"),
        ("о системе ордеров", "Ордера"),
        ("обеспечении неприкосновенности", "Неприкосновенность"),
        ("о сенате", "Сенат"),
        ("генерального прокурора", "Прокуратура"),
        ("полицейском департаменте", "LSPD"),
        ("департаменте шерифа", "LSSD"),
        ("управлении тюрем", "SASPA"),
        ("экстренной медицинской", "EMS"),
        ("федеральном расследовательском", "FIB"),
        ("национальной гвардии", "NG"),
        ("средствах массовой информации", "СМИ"),
        ("противодействии терроризму", "Терроризм"),
        ("противодействии экстремистской", "Экстремизм"),
        ("обороте оружия", "Оружие"),
        ("о предпринимательской", "Бизнес"),
        ("об аренде", "Аренда"),
        ("о судебной системе", "Суд. система"),
        ("о чрезвычайном", "ЧП"),
        ("о государственной тайне", "Гостайна"),
        ("о наградах", "Награды"),
        ("о рыболовстве", "Рыболовство"),
        ("об охоте", "Охота"),
        ("о пенсионном", "Пенсии"),
        ("об обращениях", "Обращения"),
        ("о собраниях", "Митинги"),
        ("о секретной службе", "USSS"),
        ("об оперативно-розыскной", "ОРД"),
        ("о совете национальной", "СНБ"),
        ("об ответственном обращении", "Животные"),
        ("о политических партиях", "Партии"),
        ("о деятельности офиса", "Прокуратура"),
        ("о деятельности секретной", "USSS"),
        ("о деятельности экстренной", "EMS"),
        ("об управлении тюрем", "SASPA"),
        ("о департаменте шерифа", "LSSD"),
        ("о полицейском департаменте", "LSPD"),
        ("о федеральном расследовательском", "FIB"),
    ]
    for key, val in rules:
        if key in t:
            return val
    return title[:32]


lines = SRC.read_text(encoding="utf-8").splitlines()
docs = []
cur_doc = None
cur_art = None
section = "laws"


def flush_art():
    global cur_art
    if cur_doc is not None and cur_art is not None:
        cur_doc["articles"].append(cur_art)
        cur_art = None


def flush_doc():
    global cur_doc
    flush_art()
    if cur_doc is None:
        return
    if not cur_doc["articles"]:
        body = "\n".join(
            l for l in cur_doc.get("preamble", []) if not re.fullmatch(r"-{10,}", l.strip())
        )
        chunks = []
        cur = None
        for line in body.splitlines():
            m = NUM_RE.match(line)
            if m:
                if cur:
                    chunks.append(cur)
                cur = {"num": m.group(1), "title": m.group(2).strip(), "lines": []}
            elif cur:
                cur["lines"].append(line)
        if cur:
            chunks.append(cur)
        if not chunks:
            chunks = [{"num": "0", "title": cur_doc["title"], "lines": body.splitlines()}]
        cur_doc["articles"] = chunks
    docs.append(cur_doc)
    cur_doc = None


for line in lines:
    if line.startswith("ЧАСТЬ II."):
        section = "docs"
    elif line.startswith("ЧАСТЬ I."):
        section = "laws"
    m = DOC_RE.match(line)
    if m:
        flush_doc()
        cur_doc = {
            "num": int(m.group(1)),
            "part": m.group(2),
            "laws": section == "laws",
            "title": m.group(3).strip(),
            "url": "",
            "articles": [],
            "preamble": [],
        }
        cur_art = None
        continue
    if cur_doc is None:
        continue
    if line.startswith("http") and not cur_doc["url"]:
        cur_doc["url"] = line.strip()
        continue
    am = ART_RE.match(line)
    if am:
        flush_art()
        cur_art = {"num": am.group(1), "title": am.group(2).strip(), "lines": []}
        continue
    if cur_art is not None:
        cur_art["lines"].append(line)
    else:
        cur_doc["preamble"].append(line)

flush_doc()

def clean_text(text: str) -> str:
    lines = text.splitlines()
    while lines and re.match(
        r"^\s*(?:ГЛАВА|Глава|Раздел|РАЗДЕЛ|§|Подраздел|ПОДРАЗДЕЛ)\b", lines[-1]
    ):
        lines.pop()
    return "\n".join(lines).strip()


by_id = {}
for d in docs:
    d["short"] = short_title(d["title"], "42" if d.get("laws") else "f")
    doc_key = f'{d["part"]}-{d["num"]}'
    for a in d["articles"]:
        body = "\n".join(a.get("lines", [])).strip()
        title = a.get("title", "").strip()
        text = clean_text((title + ("\n" + body if body else "")).strip())
        if not text:
            continue
        aid = f'{doc_key}/{a["num"]}'
        item = {
            "id": aid,
            "doc_key": doc_key,
            "doc_part": d["part"],
            "doc_num": d["num"],
            "doc_title": d["title"],
            "doc_short": d["short"],
            "url": d["url"],
            "article": a["num"],
            "article_title": a["title"],
            "text": text,
        }
        old = by_id.get(aid)
        if old is None:
            by_id[aid] = item
        elif item["text"] not in old["text"] and old["text"] not in item["text"]:
            old["text"] = old["text"] + "\n\n— — —\n\n" + item["text"]
        elif len(item["text"]) > len(old["text"]):
            old["text"] = item["text"]
articles = list(by_id.values())

out = ROOT / "index.json"
out.write_text(json.dumps(articles, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"docs: {len(docs)}")
print(f"articles: {len(articles)}")
print(f"index: {out} ({out.stat().st_size / 1024:.0f} KB)")
