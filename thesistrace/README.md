# ThesisTrace

A research workflow tool that makes uncertainty visible before a conclusion is trusted.
You write the question, list the assumptions the answer depends on, and label each one
**supported**, **mixed** or **unverified**. A live evidence summary tells a reviewer, at a
glance, what is proven, what is uncertain and what still needs a source.

It does not give financial advice or predict markets. It makes the reasoning behind a
financial conclusion easier to see and easier to challenge.

**Try it:** [ryanwien.github.io/thesistrace](https://ryanwien.github.io/thesistrace/). It
runs entirely in your browser, starts with a sample note about a fictional company, and
keeps your notes on your device only.

## Why it matters

Investment memos, credit write-ups and board papers usually present a conclusion with
its assumptions folded into prose. The reviewer cannot tell which claims were checked
against a filing and which were carried over from a call or a hunch. ThesisTrace keeps
that distinction on the page and refuses to blur it: evidence you cannot point at is,
by definition, unverified.

## How it works

```
ResearchNote ── question, context, tentative conclusion
   └── Assumption ×N ── statement, evidence label, source, rationale, load-bearing flag
            │
            ▼
   summarize(note) ── counts, whole-number shares, verdict,
                      proven / uncertain / needs-a-source lists
```

- `domain.py` – the vocabulary and its rules. Supported or mixed evidence must cite a source.
- `summary.py` – a pure function from a note to its evidence summary.
- `store.py` – the in-memory store; every change swaps a whole immutable note under a lock.
- `api.py` – FastAPI + Pydantic. Every response that carries a note carries its summary.
- `index.html`, `assets/` – plain HTML, CSS and JS, no build step. The page sends every
  change to the API and shows what comes back; it does not judge evidence itself.
- `assets/engine.js` – the same rules in JavaScript, with the same routes and responses.
  When the page finds no server (as on GitHub Pages), its requests go here instead and
  notes are saved in the browser.

### Verdict, most severe first

| Verdict | When |
|---|---|
| Not ready | A load-bearing assumption has no source |
| Needs sources | Some assumption has no source |
| Contested | Everything is sourced, but some evidence is mixed |
| Supported | Everything is sourced and supported |

## Run

```bash
pip install -r requirements.txt -e .
python -m thesistrace.api      # http://127.0.0.1:8000, with a sample note loaded
pytest                         # flow, domain, and engine.js parity (needs Node for parity)
python -m thesistrace.run      # regenerates results/
```

Without Python, serve the folder with any static file server and open `index.html`; the
page switches to the in-browser engine on its own. Run the server from this checkout
(or an editable install): it serves the page from the project folder.

## Results

From `results/` (sample note about a fictional company): 5 assumptions, 2 supported,
1 mixed, 2 unverified. One load-bearing assumption has no source, so the verdict is
**Not ready**. See [`results/REPORT.md`](results/REPORT.md).

## Decisions

- **Source required for supported and mixed.** Enforced in the domain, not just the form,
  so the API cannot be used to record unsupported confidence.
- **Load-bearing flag.** Not every gap matters equally. A missing source on an assumption
  the conclusion depends on blocks the verdict; a peripheral one only lowers it.
- **One set of rules, two engines, tested against each other.** Python is the reference.
  The browser engine exists so the tool works on static hosting, and
  `tests/test_engine_parity.py` runs it under Node against Python on every small note,
  the sample note and a full request sequence, so the two cannot drift silently.
- **The page never judges evidence.** Whichever engine answers, the page only shows the
  summary it is given.
- **Shares use largest-remainder rounding** so the three percentages always add up to 100.

## Limitations

- With the server, notes live in memory; a restart clears everything except the sample.
- In the browser, notes stay in that browser on that device. Clearing site data removes
  them, and they cannot be shared with a reviewer yet.
- Labels reflect the analyst's judgement; nothing checks that a cited source says what
  the analyst claims it says.
- One person at a time: there are no accounts, edit history or reviewer comments.

## What I'd do next

- SQLite persistence with an append-only change log, so a reviewer can see when a label
  moved and who moved it.
- Reviewer sign-off per assumption, separate from the author's label.
- Links from a source citation to the exact filing page, with a staleness date.
