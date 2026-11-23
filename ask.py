import json
import math
import queue
import re
import sys
import threading
import time
from pathlib import Path

import requests

try:
    import pymorphy3

    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:
    _MORPH = None

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stdin:
    sys.stdin.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.json"
LOCAL_ENV = ROOT / ".env"

articles = json.loads(INDEX.read_text(encoding="utf-8"))
TEMPLATES = []
_tpl_path = ROOT / "templates.json"
if _tpl_path.exists():
    TEMPLATES = json.loads(_tpl_path.read_text(encoding="utf-8"))

TOKEN_RE = re.compile(r"[a-zа-я0-9]+", re.I)
STOP = set(
    "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между".split()
)
SUFFIXES = sorted(
    "иями ями ами иях иям ией ием ия ию ии ов ев ий ый ая ое ые их ых ому ему ого его ыми ими ой ей ом ем ах ях а я ы и о е у ю".split(),
    key=len,
    reverse=True,
)


def norm(s: str) -> str:
    return s.lower().replace("ё", "е")


STEM_MAP = {
    "обыскать": "обыск",
    "обыскал": "обыск",
    "обыскала": "обыск",
    "обыскали": "обыск",
    "досмотреть": "досмотр",
    "досмотрел": "досмотр",
    "досмотрела": "досмотр",
    "досмотрели": "досмотр",
    "остановить": "останов",
    "остановил": "останов",
    "остановила": "останов",
    "остановили": "останов",
    "задержать": "задержан",
    "задержал": "задержан",
    "задержала": "задержан",
    "задержали": "задержан",
    "допросить": "допрос",
    "допросил": "допрос",
    "допросили": "допрос",
    "применить": "примен",
    "применил": "примен",
    "применили": "примен",
    "изъять": "изъят",
    "изъял": "изъят",
    "изъяли": "изъят",
}


def stem(w: str) -> str:
    if w in STEM_MAP:
        return STEM_MAP[w]
    for s in SUFFIXES:
        if len(w) > len(s) + 2 and w.endswith(s):
            return w[: -len(s)]
    return w


def tokens(s: str) -> list[str]:
    return [stem(t) for t in TOKEN_RE.findall(norm(s)) if len(t) > 1 and t not in STOP]


LEMMA_CACHE = ROOT / "lemmas.json"
_LEMMA_SETS = None


def _lemma(w: str) -> str:
    if _MORPH is not None:
        return _MORPH.parse(w)[0].normal_form
    return stem(w)


def lemmatize(text: str) -> set[str]:
    out = set()
    for w in TOKEN_RE.findall(norm(text)):
        if len(w) <= 1 or w in STOP:
            continue
        out.add(_lemma(w))
    return out


ABBREV = {
    "генпрок": "генеральный прокурор",
    "генпрокурор": "генеральный прокурор",
    "генпрокуратура": "генеральный прокурор",
}


def query_terms(q: str, typing: bool = False) -> list[tuple[str, set[str], str | None]]:
    raw = TOKEN_RE.findall(norm(q))
    ends_space = bool(q) and q[-1].isspace()
    words = [w for w in raw if (len(w) > 1 or typing) and w not in STOP]
    if typing and not ends_space and raw and (not words or words[-1] != raw[-1]):
        words.append(raw[-1])
    if words:
        expanded: list[str] = []
        for w in words:
            full = None
            for short, long in ABBREV.items():
                if w == short or (len(w) >= 3 and short.startswith(w)):
                    full = long
                    break
            expanded.extend((full or w).split())
        words = expanded
    index: dict[str, dict] = {}
    order: list[str] = []
    for pos, w in enumerate(words):
        parsed = _MORPH.parse(w)[0] if _MORPH is not None else None
        lemma = parsed.normal_form if parsed is not None else stem(w)
        forms = {f.word.lower() for f in parsed.lexeme} if parsed is not None else {w.lower()}
        forms.add(w.lower())
        prefix = None
        if parsed is not None:
            known = getattr(parsed, "is_known", True)
            if not known:
                prefix = w
            if typing and pos == len(words) - 1 and not ends_space:
                prefix = w
        else:
            prefix = w
        if lemma in index:
            index[lemma]["forms"].update(forms)
            if prefix and not index[lemma]["prefix"]:
                index[lemma]["prefix"] = prefix
        else:
            index[lemma] = {"forms": forms, "prefix": prefix}
            order.append(lemma)
    return [
        (lemma, index[lemma]["forms"], index[lemma]["prefix"]) for lemma in order
    ]


def query_info(q: str) -> tuple[list[str], list[str]]:
    terms = query_terms(q)
    return [t for t, _, _ in terms], sorted({f for _, fs, _ in terms for f in fs})


def get_lemma_sets() -> list[set[str]]:
    global _LEMMA_SETS
    if _LEMMA_SETS is not None:
        return _LEMMA_SETS
    if _MORPH is None:
        _LEMMA_SETS = [
            set(tokens(a["text"] + " " + a["article_title"] + " " + a["doc_title"]))
            for a in articles
        ]
        return _LEMMA_SETS
    if LEMMA_CACHE.exists():
        try:
            data = json.loads(LEMMA_CACHE.read_text(encoding="utf-8"))
            if len(data) == len(articles):
                _LEMMA_SETS = [set(x) for x in data]
                return _LEMMA_SETS
        except Exception:
            pass
    data = []
    for a in articles:
        data.append(sorted(lemmatize(a["text"] + " " + a["article_title"] + " " + a["doc_title"])))
    LEMMA_CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _LEMMA_SETS = [set(x) for x in data]
    return _LEMMA_SETS


SYNONYMS = {
    "пускают": ["допуск", "допускаются", "адвокат"],
    "пускать": ["допуск"],
    "задержанному": ["задержание", "задержанный"],
    "задержанного": ["задержание", "задержанный"],
    "задержали": ["задержание", "задержанный"],
    "держать": ["срок", "час"],
    "держат": ["срок", "час"],
    "машину": ["автомобиль", "транспорт"],
    "машина": ["автомобиль", "транспорт"],
    "квартиру": ["жилище"],
    "квартира": ["жилище"],
    "телефон": ["переписка", "переговоры", "сообщения"],
    "права": ["миранда", "разъяснение"],
    "адвокат": ["защитник", "допуск", "встреча"],
    "обыск": ["досмотр", "изъятие", "выемка"],
    "досмотр": ["обыск", "изъятие", "выемка"],
    "гараж": ["нежил", "помещен"],
    "авто": ["автомобил", "транспорт"],
    "багажник": ["транспорт", "автомобил", "обыск"],
    "ордер": ["разрешение", "санкция"],
    "сила": ["оружие", "спецсредства"],
    "обжаловать": ["обжалование", "жалоба"],
}

PHRASES = [
    ("не пускают", "допуск адвокат задержанный"),
    ("не пускает", "допуск адвокат задержанный"),
    ("обыск машин", "обыск транспорт автомобиль"),
    ("обыскать машин", "обыск транспорт автомобиль"),
    ("остановили авто", "обыск транспорт автомобиль"),
    ("досмотрели багажник", "обыск транспорт автомобиль"),
    ("обыскать гараж", "обыск нежилое помещение гараж"),
    ("гараж", "нежилое помещение"),
    ("квартир", "жилище"),
    ("телефон", "переписка переговоры сообщения"),
    ("без прав", "миранда разъяснение"),
    ("без объяснения", "основание задержание"),
    ("сколько держать", "срок задержание час"),
    ("сколько могут держать", "срок задержание час"),
    ("сколько можно держать", "срок задержание час"),
    ("сколько держат", "срок задержание час"),
    ("применили силу", "применение силы оружие"),
    ("изъяли", "изъятие протокол"),
    ("обжаловать", "обжалование жалоба"),
]


def expand_query(q: str) -> list[str]:
    qn = norm(q)
    terms = tokens(qn)
    for w in list(terms):
        for syn in SYNONYMS.get(w, []):
            terms.extend(tokens(syn))
    for pat, extra in PHRASES:
        if pat in qn:
            terms.extend(tokens(extra))
    return terms


def match_template(q: str) -> dict | None:
    qn = norm(q)
    best = None
    best_score = 0
    for t in TEMPLATES:
        if any(norm(n) in qn for n in t.get("negatives", [])):
            continue
        hits = sum(1 for k in t["keywords"] if norm(k) in qn)
        if hits >= t.get("min_hits", 2) and hits > best_score:
            best = t
            best_score = hits
    return best


def template_prior(q: str) -> dict:
    qn = norm(q)
    boosts = {}
    for t in TEMPLATES:
        hits = sum(1 for kw in t["keywords"] if norm(kw) in qn)
        if hits >= 2:
            for doc, art, part in t["cites"]:
                key = (doc, art)
                boosts[key] = max(boosts.get(key, 0.0), hits * 3.0)
    return boosts


doc_tokens = []
for a in articles:
    text = a["doc_short"] + " " + a["doc_title"] + " " + a["article_title"] + " " + a["text"]
    toks = tokens(text)
    toks += tokens(a["doc_short"] + " " + a["article_title"]) * 2
    doc_tokens.append(toks)

N = len(doc_tokens)
avgdl = sum(len(d) for d in doc_tokens) / N
df: dict[str, int] = {}
for toks in doc_tokens:
    for t in set(toks):
        df[t] = df.get(t, 0) + 1
idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
tfs = []
for toks in doc_tokens:
    tf: dict[str, int] = {}
    for t in toks:
        tf[t] = tf.get(t, 0) + 1
    tfs.append(tf)


DOC_PRIOR = {
    "ПК": 1.2,
    "УК": 0.8,
    "КоАП": 0.8,
    "Адвокатура": 1.0,
    "Конституция": 0.6,
    "Неприкосновенность": 0.6,
    "Ордера": 0.6,
    "Правительство": 0.3,
}


def score_bonus(q: str, a: dict) -> float:
    qn = norm(q)
    title = norm(a["article_title"])
    text = norm(a["text"])
    doc = a["doc_short"]
    b = DOC_PRIOR.get(doc, 0.0)

    if "обыск" in qn and "обыск" in title:
        b += 3.0
    if "задержан" in qn and "задержан" in title:
        b += 2.0
    if (
        ("сколько" in qn or "держать" in qn or "срок" in qn)
        and doc == "ПК"
        and a["article"] in ("15", "20")
        and ("освобожд" in title or "1 часа" in text or "1 час" in text)
    ):
        b += 2.5
    if ("адвокат" in qn or "защитник" in qn or "допуск" in qn) and (
        "адвокат" in title or doc == "Адвокатура"
    ):
        b += 2.0
    if ("права" in qn or "миранда" in qn) and ("права" in title or "миранда" in text):
        b += 1.5
    if "допрос" in qn and ("допрос" in title or "допрос" in text):
        b += 1.5
    if ("квартир" in qn or "жилищ" in qn) and "жилищ" in title:
        b += 3.0
    if ("телефон" in qn or "переписк" in qn) and (
        "переписк" in title or "переписк" in text
    ):
        b += 2.0

    if ("квартир" in qn or "жилищ" in qn) and doc != "ПК":
        b -= 1.0
    if ("обыск" in qn or "машин" in qn or "автомобил" in qn) and doc not in ("ПК", "ДК", "УК"):
        b -= 1.0
    if "задержан" in qn and doc not in ("ПК", "УК", "КоАП", "Адвокатура", "Неприкосновенность"):
        b -= 1.0

    if any(w in qn for w in ("адвокат", "защитник", "допуск", "пускают", "встреч")):
        if doc == "Адвокатура" and a["article"] in ("3", "7"):
            b += 6.0
        if doc == "ПК" and a["article"] in ("18", "22", "23"):
            b += 2.0
        if doc == "ПК" and a["article"] in ("17", "19", "20"):
            b -= 4.0
        if doc not in ("ПК", "Адвокатура", "УК", "КоАП", "Неприкосновенность", "Конституция"):
            b -= 6.0
    if "обыск" in qn or "машин" in qn or "автомобил" in qn:
        if doc == "ПК" and a["article"] in ("30", "12"):
            b += 2.0
        if doc in ("УК", "ДК", "NG", "FIB", "EMS") and "обыск" not in title:
            b -= 1.0
    if ("машин" in qn or "автомобил" in qn or "авто" in qn) and doc == "ПК" and a["article"] == "4":
        b -= 2.0
    if ("гараж" in qn or "нежил" in qn) and doc == "ПК" and a["article"] in ("4", "29", "55"):
        b += 3.0
    if "сколько" in qn or "держать" in qn:
        if doc == "ПК" and a["article"] == "20":
            b += 3.0
    return b


def bm25(q: str, k: int = 12) -> list[dict]:
    qt = expand_query(q)
    priors = template_prior(q)
    scored = []
    for i, tf in enumerate(tfs):
        dl = len(doc_tokens[i])
        s = 0.0
        for t in qt:
            f = tf.get(t, 0)
            if f:
                s += idf.get(t, 0.0) * (f * 2.5) / (f + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl))
        if s > 0:
            a = articles[i]
            s += score_bonus(q, a)
            s += priors.get((a["doc_short"], a["article"]), 0.0)
            scored.append((s, i))
    scored.sort(reverse=True)
    return [articles[i] for _, i in scored[:k]]


QUERY_CITE = re.compile(
    r"(?:(ПК|УК|КоАП|ГК|ТК|ДК|ВК|ЭК|Конституция|Адвокатура|Правительство|Ордера|Неприкосновенность|Сенат|Прокуратура)\s*)?"
    r"(?:ст\.?|статья|статьи|статье|статью)\s*(\d+(?:\.\d+)*)",
    re.I,
)
QUERY_SHORT = re.compile(r"\b(ПК|УК|КоАП|ГК|ТК|ДК|ВК|ЭК)\s*(\d+(?:\.\d+)*)", re.I)


def exact_hits(q: str) -> list[dict]:
    found = []
    seen = set()
    for rx in (QUERY_CITE, QUERY_SHORT):
        for m in rx.finditer(q):
            doc, art = m.group(1), m.group(2)
            for a in articles:
                if a["article"] != art:
                    continue
                if doc and a["doc_short"].lower() != doc.lower():
                    continue
                if a["id"] not in seen:
                    seen.add(a["id"])
                    found.append(a)
    return found


def search(q: str, k: int = 12) -> list[dict]:
    exact = exact_hits(q)
    hits = bm25(q, k)
    if exact:
        ids = {a["id"] for a in hits}
        hits = exact + [a for a in hits if a["id"] not in ids]
    return hits


_LEMMA_INDEX = None
_PREFIX_IDS: dict[str, set[int]] = {}
_INDEX_LOCK = threading.RLock()


def get_lemma_index() -> dict[str, list[int]]:
    global _LEMMA_INDEX
    if _LEMMA_INDEX is None:
        with _INDEX_LOCK:
            if _LEMMA_INDEX is None:
                index: dict[str, list[int]] = {}
                for i, ls in enumerate(get_lemma_sets()):
                    for lemma in ls:
                        index.setdefault(lemma, []).append(i)
                _LEMMA_INDEX = index
    return _LEMMA_INDEX


def prefix_ids(prefix: str) -> set[int]:
    hit = _PREFIX_IDS.get(prefix)
    if hit is not None:
        return hit
    with _INDEX_LOCK:
        hit = _PREFIX_IDS.get(prefix)
        if hit is not None:
            return hit
        ids: set[int] = set()
        for lemma, arts in get_lemma_index().items():
            if lemma.startswith(prefix):
                ids.update(arts)
        if len(_PREFIX_IDS) > 400:
            _PREFIX_IDS.clear()
        _PREFIX_IDS[prefix] = ids
    return ids


def article_body(a: dict) -> str:
    text = a["text"]
    title = a["article_title"].strip()
    if title and text.startswith(title):
        text = text[len(title) :].lstrip("\n ")
    return text


def make_snippet(body: str, start: int, end: int) -> str:
    start = max(0, min(start, len(body)))
    end = max(start, min(end, len(body)))
    if start > 0 and not body[start - 1].isspace():
        m = re.search(r"\s", body[start : start + 40])
        if m:
            start += m.end()
    if end < len(body):
        cut = max(body.rfind(" ", start, end), body.rfind("\n", start, end))
        if cut > start:
            end = cut
    sn = body[start:end].replace("\n", " ").strip()
    if start > 0:
        sn = "… " + sn
    if end < len(body):
        sn = sn + " …"
    return sn


ST_ARTICLE_RE = re.compile(
    r"(?<![а-яa-z])(?:статья|статьи|статью|статье|ст)\.?\s*(\d{1,3}(?:\.\d+)*)"
)
ST_ARTICLE_PRE_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)*)\s*(?:-?[яй])?\s*(?:статья|статьи|статью|статье|ст)\.?(?![а-яa-z])"
)
ARTICLE_NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)*)(?!\d)")

_ALIAS_RX: list[tuple[re.Pattern, str]] = []


def _make_aliases() -> list[tuple[re.Pattern, str]]:
    docs = {a["doc_short"] for a in articles}
    manual = {
        "тк": "ТК",
        "трудовой кодекс": "ТК",
        "трудового кодекса": "ТК",
        "трудовому кодексу": "ТК",
        "ук": "УК",
        "уголовный кодекс": "УК",
        "уголовного кодекса": "УК",
        "пк": "ПК",
        "процессуальный кодекс": "ПК",
        "процессуального кодекса": "ПК",
        "гк": "ГК",
        "гражданский кодекс": "ГК",
        "гражданского кодекса": "ГК",
        "дк": "ДК",
        "дорожный кодекс": "ДК",
        "дорожного кодекса": "ДК",
        "вк": "ВК",
        "воздушный кодекс": "ВК",
        "воздушного кодекса": "ВК",
        "эк": "ЭК",
        "этический кодекс": "ЭК",
        "этического кодекса": "ЭК",
        "коап": "КоАП",
        "кодекс об административных правонарушениях": "КоАП",
        "конституция": "Конституция",
        "конституции": "Конституция",
        "адвокатура": "Адвокатура",
        "адвокатуре": "Адвокатура",
        "адвокатуры": "Адвокатура",
        "прокуратура": "Прокуратура",
        "прокуратуре": "Прокуратура",
        "прокуратуры": "Прокуратура",
        "правительство": "Правительство",
        "правительстве": "Правительство",
        "сенат": "Сенат",
        "сенате": "Сенат",
        "сената": "Сенат",
        "фиб": "Устав FIB",
        "лспд": "Устав LSPD",
        "емс": "Устав EMS",
        "саспа": "Устав SASPA",
        "устав лспд": "Устав LSPD",
        "устав фиб": "Устав FIB",
        "устав емс": "Устав EMS",
        "устав саспа": "Устав SASPA",
        "устав коллегии": "Устав КА",
        "устав коллегии адвокатов": "Устав КА",
        "регламент коллегии": "Регламент КА",
        "регламент коллегии адвокатов": "Регламент КА",
        "санг": "Устав NG",
        "sang": "Устав NG",
        "условно-досрочное": "УДО",
        "условно досрочное": "УДО",
        "суд система": "Суд. система",
        "суд. система": "Суд. система",
        "судебная система": "Суд. система",
    }
    aliases: dict[str, str] = {}
    for alias, doc in manual.items():
        if doc in docs:
            aliases[norm(alias)] = doc
    for doc in docs:
        aliases.setdefault(norm(doc), doc)
        if doc.startswith('Закон "О регулировании оборота'):
            for alias in ("оружие", "оружия", "оборот оружия"):
                aliases.setdefault(alias, doc)
        elif doc.startswith("Закон “О порядке рассмотрения"):
            for alias in ("обращения граждан", "обращений граждан", "обращения"):
                aliases.setdefault(alias, doc)
    for a in articles:
        title = norm(a["doc_title"]).split("(редакция")[0].strip()
        pos = title.find("кодекс")
        if pos > 0:
            head = title[: pos + len("кодекс")].strip(' "“”«»')
            aliases.setdefault(head, a["doc_short"])
    result = []
    for alias, doc in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if len(alias) < 2:
            continue
        result.append(
            (
                re.compile(
                    r"(?<![а-яa-z])" + re.escape(alias) + r"(?![а-яa-z])"
                ),
                doc,
            )
        )
    return result


def _article_num(s: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in s.split("."))
    except ValueError:
        return (0,)


def direct_lookup(q: str, typing: bool = False) -> dict | None:
    _ensure_aliases()
    nq = norm(q)
    doc = None
    dspan = None
    for rx, name in _ALIAS_RX:
        m = rx.search(nq)
        if not m:
            continue
        if dspan is None or (m.end() - m.start()) > (dspan[1] - dspan[0]):
            doc, dspan = name, (m.start(), m.end())
    if not doc or dspan is None:
        return None

    num = None
    marker = False
    sm = ST_ARTICLE_RE.search(nq)
    if sm:
        num = sm.group(1)
        marker = True
    else:
        pm = ST_ARTICLE_PRE_RE.search(nq)
        if pm:
            num = pm.group(1)
            marker = True
    if num is None:
        def only_filler(s: str) -> bool:
            return not re.sub(r"[^а-яa-z0-9]+", "", BROWSE_FILLER.sub(" ", s))

        for nm in ARTICLE_NUM_RE.finditer(nq):
            before = nm.end() <= dspan[0] and only_filler(nq[nm.end() : dspan[0]])
            after = dspan[1] <= nm.start() and only_filler(nq[dspan[1] : nm.start()])
            if before or after:
                cuts = sorted([(dspan[0], dspan[1]), (nm.start(), nm.end())])
                left = ""
                prev = 0
                for a, b in cuts:
                    left += nq[prev:a] + " "
                    prev = b
                left += nq[prev:]
                left = BROWSE_FILLER.sub(" ", left)
                if re.sub(r"[^а-яa-z0-9]+", "", left):
                    continue
                num = nm.group(1)
                break
    if not num:
        return None
    if typing and not marker and re.search(r"\d\.?$", nq.strip()):
        return _browse_result(doc, q)

    found = [
        i
        for i, a in enumerate(articles)
        if a["doc_short"] == doc and a["article"] == num
    ]
    result = {
        "query": q,
        "typing": False,
        "direct": True,
        "doc": doc,
        "article_num": num,
        "missing": not found,
        "terms": [],
        "forms": [],
        "prefixes": [],
        "items": [],
        "total": 0,
    }
    if found:
        i = found[0]
        a = articles[i]
        body = article_body(a)
        result["items"] = [
            {
                "idx": i,
                "doc": a["doc_short"],
                "article": a["article"],
                "title": a["article_title"],
                "snippet": make_snippet(body, 0, 320),
                "score": 0,
            }
        ]
        result["total"] = 1
        return result

    target = _article_num(num)
    pool = [(i, a) for i, a in enumerate(articles) if a["doc_short"] == doc]
    pool.sort(
        key=lambda x: (
            abs(_article_num(x[1]["article"])[0] - target[0]),
            _article_num(x[1]["article"]),
        )
    )
    for i, a in pool[:6]:
        body = article_body(a)
        result["items"].append(
            {
                "idx": i,
                "doc": a["doc_short"],
                "article": a["article"],
                "title": a["article_title"],
                "snippet": make_snippet(body, 0, 240),
                "score": 0,
            }
        )
    result["total"] = len(result["items"])
    return result


BROWSE_FILLER = re.compile(
    r"(?:статьи|статья|статью|статье|статей|статьям|статьями|статьях|ст|все|всё|список|закон|закона|кодекс|кодекса|об|о)(?![а-яa-z])"
)


def _browse_result(doc: str, q: str) -> dict:
    pool = [(i, a) for i, a in enumerate(articles) if a["doc_short"] == doc]
    pool.sort(key=lambda x: _article_num(x[1]["article"]))
    items = []
    for i, a in pool:
        body = article_body(a)
        items.append(
            {
                "idx": i,
                "doc": a["doc_short"],
                "article": a["article"],
                "title": a["article_title"],
                "snippet": make_snippet(body, 0, 200),
                "score": 0,
            }
        )
    return {
        "query": q,
        "typing": False,
        "browse": True,
        "doc": doc,
        "terms": [],
        "forms": [],
        "prefixes": [],
        "items": items,
        "total": len(items),
    }


def browse_lookup(q: str) -> dict | None:
    _ensure_aliases()
    nq = norm(q)
    doc = None
    dspan = None
    for rx, name in _ALIAS_RX:
        m = rx.search(nq)
        if m and (dspan is None or (m.end() - m.start()) > (dspan[1] - dspan[0])):
            doc, dspan = name, (m.start(), m.end())
    if not doc or dspan is None or ARTICLE_NUM_RE.search(nq):
        return None
    rest = BROWSE_FILLER.sub(" ", nq[: dspan[0]] + " " + nq[dspan[1] :])
    if re.sub(r"[^а-яa-z0-9]+", "", rest):
        return None
    return _browse_result(doc, q)


_BUILD_ALIASES_DONE = False


def _ensure_aliases() -> None:
    global _BUILD_ALIASES_DONE
    if _BUILD_ALIASES_DONE:
        return
    with _INDEX_LOCK:
        if not _BUILD_ALIASES_DONE:
            built = _make_aliases()
            _ALIAS_RX[:] = built
            _BUILD_ALIASES_DONE = True


DOC_PRIO = {
    "ПК": 5,
    "УК": 4,
    "КоАП": 4,
    "Адвокатура": 4,
    "Конституция": 3,
    "Правительство": 3,
    "Неприкосновенность": 3,
    "Ордера": 3,
    "Прокуратура": 2,
    "Сенат": 2,
}


def term_pattern(prefix: str | None, forms: set[str]) -> re.Pattern:
    if prefix:
        return re.compile(
            r"(?<![а-яё])" + re.escape(prefix) + r"[а-яё]*(?![а-яё])", re.I
        )
    return re.compile(
        r"(?<![а-яё])(?:"
        + "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
        + r")(?![а-яё])",
        re.I,
    )


def search_articles(q: str, typing: bool = False) -> dict:
    direct = direct_lookup(q, typing)
    if direct is not None:
        direct["typing"] = typing
        return direct
    browse = browse_lookup(q)
    if browse is not None:
        browse["typing"] = typing
        return browse
    term_forms = query_terms(q, typing)
    result = {
        "query": q,
        "typing": typing,
        "terms": [],
        "forms": [],
        "prefixes": [],
        "items": [],
        "total": 0,
    }
    if not term_forms:
        return result

    lemmas = [t for t, _, _ in term_forms]
    forms = sorted({f for _, fs, _ in term_forms for f in fs})
    effective = []
    for lemma, fs, prefix in term_forms:
        if prefix and not prefix_ids(prefix):
            effective.append((lemma, fs, None))
        else:
            effective.append((lemma, fs, prefix))
    prefixes = [p for _, _, p in effective if p]
    result.update(terms=lemmas, forms=forms, prefixes=prefixes)

    candidates = None
    for lemma, fs, prefix in effective:
        ids = prefix_ids(prefix) if prefix else set(get_lemma_index().get(lemma, ()))
        candidates = ids if candidates is None else candidates & ids
        if not candidates:
            if not typing:
                alt = search_articles(q, typing=True)
                alt["typing"] = False
                return alt
            return result
    limit = 80 if (typing or prefixes) else None

    patterns = [term_pattern(p, fs) for _, fs, p in effective]

    scored = []
    for i in sorted(candidates):
        a = articles[i]
        body = article_body(a)
        body_n = norm(body)
        title_n = norm(a["article_title"])
        title_hit = any(rx.search(title_n) for rx in patterns)
        if typing:
            counts = [len(rx.findall(body_n)) for rx in patterns]
            score = (
                sum(min(c, 20) for c in counts)
                + DOC_PRIO.get(a["doc_short"], 0)
                + (12 if title_hit else 0)
            )
            sn = ""
        else:
            positions = []
            for rx in patterns:
                ps = [m.start() for m in rx.finditer(body_n)]
                if not ps:
                    positions = []
                    break
                positions.append(ps[:120])
            best = None
            if positions:
                if len(positions) == 1:
                    best = (0, positions[0][0], positions[0][0])
                else:
                    spans = sorted({p for ps in positions for p in ps})
                    for start in spans:
                        end = start + 260
                        if not all(any(start <= p <= end for p in ps) for ps in positions):
                            continue
                        inner = [p for ps in positions for p in ps if start <= p <= end]
                        span = max(inner) - min(inner)
                        if best is None or span < best[0]:
                            best = (span, min(inner), max(inner))
            if best is None:
                if not title_hit:
                    continue
                flat = body.replace("\n", " ").strip()
                sn = f'{a["doc_title"]} — {a["article_title"]} — {flat[:160]}'
                if len(flat) > 160:
                    sn += " …"
                score = DOC_PRIO.get(a["doc_short"], 0) + 10 + len(patterns)
            else:
                span, minp, maxp = best
                sn = make_snippet(body, minp - 80, maxp + 180)
                score = (
                    sum(len(ps) for ps in positions)
                    + DOC_PRIO.get(a["doc_short"], 0)
                    + (12 if title_hit else 0)
                    + max(0, 8 - span // 40)
                )
        scored.append(
            {
                "idx": i,
                "doc": a["doc_short"],
                "article": a["article"],
                "title": a["article_title"],
                "snippet": sn,
                "score": score,
            }
        )

    scored.sort(key=lambda x: (-x["score"], x["doc"], _article_num(x["article"])))
    if not scored and not typing:
        alt = search_articles(q, typing=True)
        alt["typing"] = False
        return alt
    result["total"] = len(scored)
    result["items"] = scored[:limit] if limit else scored
    if typing:
        for it in result["items"]:
            body = article_body(articles[it["idx"]])
            body_n = norm(body)
            first = None
            for rx in patterns:
                m = rx.search(body_n)
                if m and (first is None or m.start() < first):
                    first = m.start()
            it["snippet"] = make_snippet(body, (first or 0) - 100, (first or 0) + 220)
    return result


SYS = """Ты — помощник государственного адвоката на ролевом сервере GTA5RP (Blaine, вымышленный штат). Реальное право РФ/США не применять.
Я государственный адвокат. Ниже — выдержки из корпуса. Используй только их. Не выдумывай номера статей, части и цитаты.
Напиши готовую фразу от первого лица, максимум 3 предложения и 450 символов, которую я прочитаю вслух. Ссылки на нормы — прямо в тексте, словами, без аббревиатур: «по статье 7 части 1 закона „Об адвокатуре“», «по статье 22 части 1 пункту „д“ Процессуального кодекса». Всегда указывай статью, часть и пункт, если они есть. Не путай часть и пункт: часть — это «часть 2», пункт — это «пункт 5». Пример: право адвоката на встречу — это статья 3 часть 2 пункт 5 закона «Об адвокатуре», а не «часть 5». Если норма содержит перечень, не выдёргивай из него отдельные пункты: либо перечисли все, либо скажи «в случаях, перечисленных в статье X». Бери только нормы, без которых фраза не держится; не перечисляй всё. Если в выдержках есть прямое противоречие — скажи об этом одной фразой. Без заголовков, списков, звёздочек и пояснений. Только фраза."""

PART_SPLIT = re.compile(r"(?m)^(?=\s*(?:ч\.\s*\d+|\d+(?:\.\d+)*[.)]|[а-я]\)))")


def snippet(a: dict, q: str, max_chars: int = 1200) -> str:
    text = a["text"].strip()
    bullets = len(re.findall(r"(?m)^\s*(?:[а-я]\)|\d+\))", text))
    if bullets >= 4 and len(text) <= 2200:
        return text
    qn = norm(q)
    qterms = set(expand_query(q))
    parts = [p.strip() for p in PART_SPLIT.split(text) if p.strip()]
    scored = []
    for idx, p in enumerate(parts):
        pn = norm(p)
        score = len(qterms & set(tokens(p)))
        for kw in ("адвокат", "задержан", "обыск", "ордер", "право", "миранда", "час", "жилищ", "переписк"):
            if kw in qn and kw in pn:
                score += 2
        if any(w in qn for w in ("адвокат", "защитник", "допуск", "пускают")) and not (
            "адвокат" in pn or "защитник" in pn
        ):
            score -= 3
        if any(w in qn for w in ("сколько", "держать", "держат", "срок")) and (
            re.search(r"\bчас", pn) or "минут" in pn
        ):
            score += 5
        scored.append((score, idx, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = []
    for s, idx, p in scored:
        if s <= 0 and chosen:
            break
        if len("\n\n".join(x[2] for x in chosen + [(s, idx, p)])) > max_chars:
            break
        chosen.append((s, idx, p))
        if len(chosen) >= 4:
            break
    if not chosen:
        chosen = [(0, 0, text[:max_chars])]
    chosen.sort(key=lambda x: x[1])
    return clip("\n\n".join(x[2] for x in chosen), max_chars)


def build_user(q: str, hits: list[dict]) -> str:
    parts = []
    for n, a in enumerate(hits, 1):
        txt = snippet(a, q)
        parts.append(f'[{n}] {a["doc_short"]} ст. {a["article"]} «{a["article_title"]}»\n{txt}')
    return f"Ситуация: {q}\n\nВыдержки:\n" + "\n\n".join(parts)


def load_env() -> dict:
    env = {}
    if not LOCAL_ENV.exists():
        return env
    for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _call_model(base: str, key: str, model: str, q: str, hits: list[dict], timeout: int = 12) -> tuple[str | None, str | None]:
    try:
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYS},
                    {"role": "user", "content": build_user(q, hits)},
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            },
            timeout=timeout,
        )
    except Exception as e:
        return None, f"{model}: network {type(e).__name__}: {str(e)[:120]}"
    if r.status_code != 200:
        return None, f"{model}: HTTP {r.status_code}: {r.text[:160]}"
    try:
        choice = r.json()["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
    except Exception as e:
        return None, f"{model}: bad response {type(e).__name__}: {str(e)[:100]}"
    content = re.sub(r"^```.*?\n|```$", "", content, flags=re.S).strip()
    if not content:
        return None, f"{model}: пустой ответ"
    return content, None


def call_llm(q: str, hits: list[dict]) -> tuple[str | None, str | None]:
    env = load_env()
    base = env.get("LLM_BASE", "https://api.closerouter.dev/v1").rstrip("/")
    key = env.get("LLM_API_KEY")
    if not key:
        return None, "нет LLM_API_KEY в .env"
    primary = env.get("LAW_MODEL", "openai/gpt-6-luna")
    fallback = env.get("LAW_FALLBACK", "openai/gpt-5.6-terra")
    models = [primary]
    if fallback and fallback != primary:
        models.append(fallback)
    if env.get("LAW_RACE", "1") == "0":
        models = [primary]

    results: queue.Queue = queue.Queue()

    def worker(model: str) -> None:
        content, err = _call_model(base, key, model, q, hits, timeout=12)
        results.put((content, err))

    for model in models:
        threading.Thread(target=worker, args=(model,), daemon=True).start()

    errors = []
    remaining = len(models)
    deadline = time.time() + 14
    while remaining > 0 and time.time() < deadline:
        try:
            content, err = results.get(timeout=max(0.1, deadline - time.time()))
        except queue.Empty:
            break
        remaining -= 1
        if content:
            return content, None
        if err:
            errors.append(err)
    tail = ("; " + "; ".join(errors[-2:])) if errors else ""
    return None, "модели не ответили за 14с" + tail


CHECK_CITE = re.compile(
    r"(?:(ПК|УК|КоАП|ГК|ТК|ДК|ВК|ЭК|Конституция|Адвокатура|Правительство|Ордера|Неприкосновенность|Сенат|Прокуратура)\s*)?"
    r"(?:ст\.?|статья|статьи|статье|статью)\s*(\d+(?:\.\d+)*)"
    r"(?:\s*(?:ч\.?|части|часть|частью)\s*(\d+))?"
    r"(?:\s*(?:п\.|пункт(?:а|у|ом)?)\s+[«\"]?([0-9]+|[а-яa-z])[»\"]?)?",
    re.I,
)


DOC_WORDS = [
    ("процессуальн", "ПК"),
    ("пк", "ПК"),
    ("уголовн", "УК"),
    ("ук", "УК"),
    ("административн", "КоАП"),
    ("коап", "КоАП"),
    ("адвокатур", "Адвокатура"),
    ("положение о губернаторе", "Правительство"),
    ("положения о губернаторе", "Правительство"),
    ("положении о губернаторе", "Правительство"),
    ("положением о губернаторе", "Правительство"),
    ("правительств", "Правительство"),
    ("системе ордеров", "Ордера"),
    ("системы ордеров", "Ордера"),
    ("неприкосновенност", "Неприкосновенность"),
    ("сенат", "Сенат"),
    ("прокуратур", "Прокуратура"),
    ("конституц", "Конституция"),
]


def find_doc(text: str, last: bool = True) -> str | None:
    t = norm(text)
    best = None
    best_pos = -1 if last else 10**9
    for w, d in DOC_WORDS:
        if len(w) <= 3:
            for m in re.finditer(rf"(?<![а-яa-z]){re.escape(w)}(?![а-яa-z])", t):
                pos = m.start()
                if (last and pos > best_pos) or (not last and pos < best_pos):
                    best_pos = pos
                    best = d
        else:
            pos = t.rfind(w) if last else t.find(w)
            if pos >= 0 and ((last and pos > best_pos) or (not last and pos < best_pos)):
                best_pos = pos
                best = d
    return best


def has_part(text: str, part: str | None) -> bool:
    if not part:
        return True
    part = str(part).strip().rstrip(".")
    return bool(re.search(rf"(?m)^\s*(?:ч\.\s*{part}\b|{part}\.)", text))


def check_template(tpl: dict) -> list[str]:
    warnings = []
    for doc, art, part in tpl.get("cites", []):
        a = next((x for x in articles if x["doc_short"] == doc and x["article"] == art), None)
        if not a:
            warnings.append(f"не найдена статья {art} в {doc}")
        elif not has_part(a["text"], part):
            warnings.append(f"в статье {art} не найдена часть {part}")
    return warnings


def check_phrase(phrase: str) -> list[str]:
    warnings = []
    last_doc = None
    last_doc_pos = 0
    for m in CHECK_CITE.finditer(phrase):
        doc, art, part, item = m.group(1), m.group(2), m.group(3), m.group(4)
        before = phrase[max(0, m.start() - 140) : m.start()]
        after = phrase[m.end() : m.end() + 80]
        doc_after_near = find_doc(after[:45], last=False)
        doc_before = find_doc(before, last=True)
        doc = doc or doc_after_near or doc_before or find_doc(after, last=False)
        if not doc and last_doc and m.start() - last_doc_pos < 600:
            doc = last_doc
        if doc:
            last_doc = doc
            last_doc_pos = m.end()
        candidates = [
            a
            for a in articles
            if a["article"] == art and (not doc or a["doc_short"].lower() == doc.lower())
        ]
        if not candidates:
            warnings.append(f"не найдена статья {art}" + (f" в {doc}" if doc else ""))
            continue
        if not doc and len(candidates) > 1:
            warnings.append(f"документ для статьи {art} не указан — проверь вручную")
            continue
        part_text = ""
        if part:
            found = False
            for a in candidates:
                if has_part(a["text"], part):
                    part_text = extract_part(a["text"], part)
                    found = True
                    break
            if not found:
                warnings.append(f"в статье {art} не найден пункт/часть {part}")
        if item:
            scope = part_text or (candidates[0]["text"] if candidates else "")
            ok = re.search(rf"(?m)^\s*{re.escape(item)}[.)]", scope) or re.search(
                rf"[«\"]{re.escape(item)}[»\"]", scope
            )
            if not ok:
                warnings.append(f"в статье {art} не найден пункт {item}")
    return warnings


def clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("\n\n", "\n", ". ", " "):
        pos = cut.rfind(sep)
        if pos > int(limit * 0.6):
            return cut[:pos].rstrip() + " …"
    return cut.rstrip() + " …"


def extract_part(text: str, part: str | None) -> str:
    if part:
        part = part.strip().rstrip(".")
        m = re.search(rf"(?m)^\s*(?:ч\.\s*{part}\b|{part}\.)", text)
        if m:
            rest = text[m.end() :]
            nxt = re.search(r"(?m)^\s*(?:ч\.\s*\d+\b|\d+\.\s)", rest)
            end = m.end() + (nxt.start() if nxt else len(rest))
            return clip(text[m.start() : end], 3000)
    return clip(text, 3000)


def law_block(phrase: str, hits: list[dict]) -> str:
    cited = []
    seen = set()
    for m in CHECK_CITE.finditer(phrase):
        doc, art, part = m.group(1), m.group(2), m.group(3)
        for a in hits:
            if a["article"] == art and (not doc or a["doc_short"].lower() == doc.lower()):
                key = (a["id"], part)
                if key not in seen:
                    seen.add(key)
                    cited.append((a, part))
                break
    if not cited:
        cited = [(a, None) for a in hits[:4]]
    out = []
    for a, part in cited[:5]:
        q = extract_part(a["text"], part)
        label = f'{a["doc_short"]} ст. {a["article"]}' + (f' ч. {part}' if part else '')
        out.append(f'- {label} — «{q}»')
    return "\n".join(out)


def law_from_cites(cites: list) -> str:
    out = []
    seen = set()
    for doc, art, part in cites:
        key = (doc, art, part)
        if key in seen:
            continue
        seen.add(key)
        a = next((x for x in articles if x["doc_short"] == doc and x["article"] == art), None)
        if not a:
            out.append(f'- {doc} ст. {art} — не найдено в индексе')
            continue
        text = extract_part(a["text"], part)
        out.append(f'- {doc} ст. {art} ч. {part} — «{text}»')
    return "\n".join(out)


def deepseek_prompt(q: str) -> tuple[str, list[dict]]:
    hits = search(q, 8)
    short = [
        {"doc": a["doc_short"], "article": a["article"], "title": a["article_title"]}
        for a in hits[:8]
    ]
    if not hits:
        return SYS + f"\n\nСитуация: {q}\n\nВ корпусе ничего не найдено.", []
    return SYS + "\n\n" + build_user(q, hits[:6]), short


def respond(q: str, no_llm: bool = False, use_templates: bool = True) -> dict:
    lookup = bool(re.match(r"^\s*(?:кто|что)\s+так", norm(q)))
    tpl = None if no_llm else (match_template(q) if (use_templates or lookup) else None)
    if tpl:
        return {
            "type": "template",
            "phrase": tpl["phrase"],
            "law": law_from_cites(tpl["cites"]),
            "warnings": check_template(tpl),
            "time": 0.0,
            "hits": [],
        }
    t0 = time.perf_counter()
    hits = search(q, 12)
    t1 = time.perf_counter()
    short = [
        {"doc": a["doc_short"], "article": a["article"], "title": a["article_title"]}
        for a in hits[:10]
    ]
    if not hits:
        return {
            "type": "empty",
            "phrase": "",
            "law": "",
            "warnings": [],
            "hits": [],
            "time": round(t1 - t0, 2),
        }
    if no_llm:
        return {
            "type": "articles",
            "phrase": "",
            "law": "",
            "warnings": [],
            "hits": short,
            "time": round(t1 - t0, 2),
        }
    phrase, err = call_llm(q, hits[:10])
    t2 = time.perf_counter()
    if err:
        return {
            "type": "error",
            "phrase": "",
            "law": "",
            "warnings": [],
            "error": err,
            "hits": short,
            "time": round(t2 - t0, 2),
        }
    warnings = check_phrase(phrase)
    t3 = time.perf_counter()
    return {
        "type": "llm",
        "phrase": phrase,
        "law": law_block(phrase, hits[:10]),
        "warnings": warnings,
        "hits": short,
        "time": round(t3 - t0, 2),
        "search_time": round(t1 - t0, 2),
        "model_time": round(t2 - t1, 2),
    }


def answer(q: str, no_llm: bool = False) -> None:
    r = respond(q, no_llm)
    if r["type"] == "template":
        print("[⚡ шаблон 0.00s]\n")
        print("ЧИТАЙ:\n«" + r["phrase"] + "»\n")
        print("ЗАКОНКА:\n" + r["law"])
        return
    if r["type"] == "empty":
        print("ничего не найдено")
        return
    if r["type"] == "articles":
        for i, a in enumerate(r["hits"][:10], 1):
            print(f'{i}. {a["doc"]} ст. {a["article"]} «{a["title"]}»')
        print(f'[⏱ поиск {r["time"]:.2f}s]')
        return
    if r["type"] == "error":
        print("LLM error:", r["error"])
        print("\nНайденные статьи:")
        for i, a in enumerate(r["hits"], 1):
            print(f'{i}. {a["doc"]} ст. {a["article"]} «{a["title"]}»')
        return
    print(
        f'[⏱ поиск {r["search_time"]:.2f}s · модель {r["model_time"]:.2f}s · итого {r["time"]:.2f}s]\n'
    )
    print("ЧИТАЙ:\n«" + r["phrase"] + "»\n")
    print("ЗАКОНКА:\n" + r["law"])
    if r["warnings"]:
        print("\n[!] проверка ссылок:")
        for w in r["warnings"]:
            print("  - " + w)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--no-llm"]
    no_llm = "--no-llm" in sys.argv
    q = " ".join(args).strip()
    if q:
        answer(q, no_llm)
        return

    print("Законка GTA5RP. Введи ситуацию, пустая строка — выход.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            break
        answer(q, no_llm)
        print()


if __name__ == "__main__":
    main()
