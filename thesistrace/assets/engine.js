/* ThesisTrace in-browser engine: the same rules as the Python package, for static hosting.
 *
 * GitHub Pages cannot run the FastAPI server, so when the page finds no API it sends every
 * request here instead. This file mirrors, rule for rule:
 *   - src/thesistrace/domain.py   (text limits, a source for supported or mixed evidence)
 *   - src/thesistrace/summary.py  (verdict order, whole percentages summing to 100,
 *                                  load-bearing assumptions listed first)
 *   - src/thesistrace/store.py    (sequential ids, all-or-nothing changes)
 *   - src/thesistrace/api.py      (routes, response shapes, error codes)
 *   - src/thesistrace/scenario.py (the sample note)
 * tests/test_engine_parity.py runs this file under Node and checks it agrees with Python.
 *
 * Works in a browser (window.ThesisEngine) and in Node (module.exports). */
(function (root) {
  "use strict";

  const LIMITS = { question: 300, statement: 500, text: 2000, source: 500, assumptions: 100 };
  const EVIDENCE = ["supported", "mixed", "unverified"];
  const HEADLINES = {
    empty: "No assumptions yet. List what the conclusion depends on.",
    blocked: "Not ready to trust: a load-bearing assumption has no source.",
    needs_sources: "Usable with care: some assumptions still need a source.",
    contested: "Every assumption is sourced, but some of the evidence is mixed.",
    supported: "Every assumption is sourced and supported.",
  };

  const SAMPLE = {
    question: "Can Larkmoor Freight Lines (fictional) keep paying its dividend through FY2027?",
    context:
      "Mid-sized regional carrier. Dividend is 40% of free cash flow today. Board review " +
      "of capital allocation is due next quarter.",
    conclusion:
      "Tentatively yes, provided freight volumes hold and the refinancing closes on the " +
      "terms in the term sheet.",
    assumptions: [
      ["Free cash flow stays above $120M a year through FY2027.", "supported",
        "FY2025 annual report, cash flow statement, p. 48",
        "Three years above $140M; guidance repeats the range.", true],
      ["The 2026 debt refinancing closes below 6.5%.", "mixed",
        "Term sheet summary in the Q3 call transcript",
        "Management quotes 6.1%; two analysts on the call expect wider spreads.", true],
      ["Freight volumes in its regions do not fall more than 5% in 2026.", "unverified",
        null, "No regional volume series found yet.", true],
      ["No large capital project is planned before FY2027.", "supported",
        "Investor day slides, capex plan, slide 12", "", false],
      ["Fuel surcharges continue to pass through to customers.", "unverified",
        null, "Contract terms not public; ask investor relations.", false],
    ],
  };

  class EngineError extends Error {
    constructor(status, code, message) {
      super(message);
      this.status = status;
      this.code = code;
    }
  }
  const invalid = (message) => new EngineError(422, "invalid_text", message);
  const notFound = (message) => new EngineError(404, "not_found", message);
  const badRequest = (message) => new EngineError(422, "invalid_request", message);

  // ---------- domain ----------

  function cleanText(value, name, limit, required) {
    if (typeof value !== "string") throw badRequest(`${name}: must be text`);
    const text = value.trim();
    if (required && !text) throw invalid(`${name} cannot be blank`);
    if (text.length > limit) throw invalid(`${name} is longer than ${limit} characters`);
    return text;
  }

  function cleanSource(value) {
    if (value === null || value === undefined) return null;
    return cleanText(value, "source", LIMITS.source, false) || null;
  }

  function makeAssumption(fields) {
    if (!EVIDENCE.includes(fields.evidence)) {
      throw badRequest(`evidence: must be one of ${EVIDENCE.join(", ")}`);
    }
    if (typeof fields.critical !== "boolean") throw badRequest("critical: must be true or false");
    const item = {
      id: fields.id,
      statement: cleanText(fields.statement, "statement", LIMITS.statement, true),
      evidence: fields.evidence,
      source: cleanSource(fields.source),
      rationale: cleanText(fields.rationale ?? "", "rationale", LIMITS.text, false),
      critical: fields.critical,
    };
    if (item.evidence !== "unverified" && item.source === null) {
      throw new EngineError(
        422,
        "missing_source",
        `an assumption marked ${item.evidence} needs a source; cite one or mark it unverified`,
      );
    }
    return item;
  }

  function makeNote(fields) {
    return {
      id: fields.id,
      question: cleanText(fields.question, "question", LIMITS.question, true),
      context: cleanText(fields.context ?? "", "context", LIMITS.text, false),
      conclusion: cleanText(fields.conclusion ?? "", "conclusion", LIMITS.text, false),
      assumptions: fields.assumptions ?? [],
    };
  }

  // ---------- summary ----------

  function wholePercentages(counts) {
    const total = EVIDENCE.reduce((sum, label) => sum + counts[label], 0);
    const shares = Object.fromEntries(EVIDENCE.map((label) => [label, 0]));
    if (total === 0) return shares;
    const remainders = {};
    for (const label of EVIDENCE) {
      shares[label] = Math.floor((counts[label] * 100) / total);
      remainders[label] = (counts[label] * 100) % total;
    }
    let left = 100 - EVIDENCE.reduce((sum, label) => sum + shares[label], 0);
    const order = [...EVIDENCE].sort(
      (a, b) => remainders[b] - remainders[a] || EVIDENCE.indexOf(a) - EVIDENCE.indexOf(b),
    );
    for (const label of order) {
      if (left-- <= 0) break;
      shares[label] += 1;
    }
    return shares;
  }

  const criticalFirst = (items) =>
    items
      .map((item, index) => [item, index])
      .sort(([a, i], [b, j]) => Number(!a.critical) - Number(!b.critical) || i - j)
      .map(([item]) => item.id);

  function summarize(note) {
    const byLabel = Object.fromEntries(EVIDENCE.map((label) => [label, []]));
    for (const item of note.assumptions) byLabel[item.evidence].push(item);
    const counts = Object.fromEntries(EVIDENCE.map((label) => [label, byLabel[label].length]));
    const unverified = byLabel.unverified;
    const criticalOpen = unverified.filter((item) => item.critical).length;
    let verdict = "supported";
    if (!note.assumptions.length) verdict = "empty";
    else if (criticalOpen) verdict = "blocked";
    else if (unverified.length) verdict = "needs_sources";
    else if (byLabel.mixed.length) verdict = "contested";
    return {
      total: note.assumptions.length,
      counts,
      shares: wholePercentages(counts),
      verdict,
      headline: HEADLINES[verdict],
      proven: criticalFirst(byLabel.supported),
      uncertain: criticalFirst(byLabel.mixed),
      needs_source: criticalFirst(unverified),
      critical_open: criticalOpen,
    };
  }

  const noteOut = (note) => ({ ...structuredClone(note), summary: summarize(note) });

  // ---------- store + routes ----------

  function rejectUnknown(body, allowed) {
    if (body === null || typeof body !== "object" || Array.isArray(body)) {
      throw badRequest("invalid request");
    }
    for (const key of Object.keys(body)) {
      if (!allowed.includes(key)) throw badRequest(`${key}: Extra inputs are not permitted`);
    }
  }

  /** Create an engine. ``storage`` has load() -> state|null and save(state). */
  function createEngine(storage = { load: () => null, save: () => {} }, { seed = true } = {}) {
    let state = storage.load();
    if (!state || !Array.isArray(state.notes)) {
      state = { notes: [], nextNote: 1, nextAssumption: 1 };
      if (seed) {
        const note = createNote(state, SAMPLE);
        for (const [statement, evidence, source, rationale, critical] of SAMPLE.assumptions) {
          addAssumption(state, note.id, { statement, evidence, source, rationale, critical });
        }
      }
      storage.save(state);
    }

    function findNote(s, id) {
      const note = s.notes.find((n) => n.id === id);
      if (!note) throw notFound(`note ${id} not found`);
      return note;
    }
    function findAssumption(note, id) {
      const item = note.assumptions.find((a) => a.id === id);
      if (!item) throw notFound(`assumption ${id} not found in note ${note.id}`);
      return item;
    }
    function createNote(s, body) {
      const note = makeNote({ ...body, id: `note-${s.nextNote}`, assumptions: [] });
      s.nextNote += 1;
      s.notes.push(note);
      return note;
    }
    function addAssumption(s, noteId, body) {
      const note = findNote(s, noteId);
      if (note.assumptions.length >= LIMITS.assumptions) {
        throw new EngineError(422, "limit_reached", `a note holds at most ${LIMITS.assumptions} assumptions`);
      }
      // Validate before drawing an id, so a rejected assumption burns no id.
      const item = makeAssumption({
        id: "draft",
        evidence: "unverified",
        source: null,
        rationale: "",
        critical: false,
        ...body,
      });
      item.id = `asm-${s.nextAssumption}`;
      s.nextAssumption += 1;
      note.assumptions.push(item);
      return note;
    }

    /** Apply ``change`` to a copy of the state; keep it only if nothing throws. */
    function transact(change) {
      const draft = structuredClone(state);
      const result = change(draft);
      state = draft;
      storage.save(state);
      return result;
    }

    const NOTE_FIELDS = ["question", "context", "conclusion"];
    const ASSUMPTION_FIELDS = ["statement", "evidence", "source", "rationale", "critical"];

    function request(method, path, body) {
      const parts = path.replace(/^\/+/, "").split("/").map(decodeURIComponent);
      if (parts[0] !== "api" || parts[1] !== "notes") throw notFound("Not Found");
      const [, , noteId, sub, assumptionId] = parts;
      const route = `${method} ${["notes", noteId && ":note", sub, assumptionId && ":asm"].filter(Boolean).join("/")}`;

      switch (route) {
        case "GET notes":
          return state.notes.map((note) => {
            const summary = summarize(note);
            return { id: note.id, question: note.question, verdict: summary.verdict, total: summary.total };
          });
        case "POST notes":
          rejectUnknown(body, NOTE_FIELDS);
          return noteOut(transact((s) => createNote(s, body)));
        case "GET notes/:note":
          return noteOut(findNote(state, noteId));
        case "PATCH notes/:note":
          rejectUnknown(body, NOTE_FIELDS);
          return noteOut(
            transact((s) => {
              const note = findNote(s, noteId);
              const changes = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== null));
              Object.assign(note, makeNote({ ...note, ...changes }));
              return note;
            }),
          );
        case "DELETE notes/:note":
          transact((s) => {
            findNote(s, noteId);
            s.notes = s.notes.filter((n) => n.id !== noteId);
          });
          return null;
        case "GET notes/:note/summary":
          return summarize(findNote(state, noteId));
        case "POST notes/:note/assumptions":
          rejectUnknown(body, ASSUMPTION_FIELDS);
          return noteOut(transact((s) => addAssumption(s, noteId, body)));
        case "PATCH notes/:note/assumptions/:asm":
          rejectUnknown(body, ASSUMPTION_FIELDS);
          return noteOut(
            transact((s) => {
              const note = findNote(s, noteId);
              const current = findAssumption(note, assumptionId);
              // null clears the source; for every other field null means "leave it".
              const changes = Object.fromEntries(
                Object.entries(body).filter(([key, value]) => key === "source" || value !== null),
              );
              const updated = makeAssumption({ ...current, ...changes, id: current.id });
              note.assumptions = note.assumptions.map((a) => (a.id === current.id ? updated : a));
              return note;
            }),
          );
        case "DELETE notes/:note/assumptions/:asm":
          return noteOut(
            transact((s) => {
              const note = findNote(s, noteId);
              findAssumption(note, assumptionId);
              note.assumptions = note.assumptions.filter((a) => a.id !== assumptionId);
              return note;
            }),
          );
        default:
          throw notFound("Not Found");
      }
    }

    return { request, summarize };
  }

  /** Storage in this browser only; every access is guarded, since it can be blocked. */
  function browserStorage(key = "thesistrace:v1") {
    return {
      load() {
        try {
          return JSON.parse(root.localStorage.getItem(key));
        } catch {
          return null;
        }
      },
      save(state) {
        try {
          root.localStorage.setItem(key, JSON.stringify(state));
        } catch {
          /* private mode or full storage: keep working in memory */
        }
      },
    };
  }

  const api = { createEngine, browserStorage, summarize, wholePercentages, EngineError, SAMPLE, LIMITS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ThesisEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
