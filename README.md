# Zakonka

Offline legal assistant for a GTA RP server's law book. A lawyer roleplayer asks a question in Russian, gets an answer with exact article citations, and can paste a ready-to-say phrase into game chat. Ships as a Windows desktop app with a live-typing overlay.

This is a roleplay tool, not legal advice. The corpus is the server's rulebook (40 documents, 1,842 articles), not real-world legislation.

## How it works

- `build_index.py` parses the corpus into `index.json` (id = document / article / part / clause) and `lemmas.json`.
- `ask.py` runs BM25 over the local index, takes the top 6 articles (~2.5 KB), and sends them to an LLM with a strict citation format: every claim must point to an article, part and clause.
- Two models race per request: first valid answer wins, 12 s per-request cap, 14 s global stop.
- Common situations are answered from verified templates instantly, without a model call.
- If the relay fails, the app degrades to showing the retrieved articles instead of an answer.
- `overlay.py` / `overlay.html` put a transparent overlay over the game for live typing.

## Numbers (last runs, Nov 2026)

- 12-query run: 12/12 answered, p50 4.2 s, max 5.2 s.
- Model benchmark: 24 of the 76 text models on the relay were tested on a control query — 3 timed out, 3 returned empty, 1 answered in the wrong language, 17 were usable. Raw results are in `tests/bench.jsonl` and `tests/results.jsonl`.
- Retrieval is local and effectively instant; the relay is the bottleneck (3.5–4 s even for short answers).

## Known issues

This repo starts with a single commit on purpose: the project lived in local folders with no version control, and getting that fixed is the point.

- No CI; tests are scripts, not a suite.
- `index.json` / `lemmas.json` are generated and baked into the exe at build time. A corpus update means a hand-run PyInstaller + Inno Setup sequence, with no version manifest and no rollback.
- The relay is a single point of failure: both racing models sit behind it, so one 502 kills both.
- The relay key is read from `.env` (not committed), but the build bundles whatever `.env` is present — key handling needs to be fixed before this goes anywhere.
- No telemetry, one user.

## Roadmap

- repo + CI on push, lockfile, one-command build
- externalized versioned data with a manifest
- second provider behind the relay, circuit breaker, cached last-known-good answer
- 100-case golden set labeled by the lawyer, template and LLM metrics split

## Run locally

```
pip install -r requirements.txt
# .env:
# LLM_BASE=https://...
# LLM_API_KEY=...
# LAW_MODEL=openai/gpt-6-luna
python build_index.py
python ask.py
```

The corpus and the generated index are not included in this repo.

## Layout

- `ask.py` — answer pipeline and CLI
- `build_index.py` — corpus → index + lemmas
- `overlay.py`, `overlay.html` — live-typing overlay
- `templates.json` — instant answers for recurring situations
- `tests/` — model benchmark and query runs (raw results included)
- `tools/` — model listing helpers
- `Zakonka.spec`, `zakonka.iss` — PyInstaller and Inno Setup configs
