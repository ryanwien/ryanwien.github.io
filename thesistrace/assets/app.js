/* ThesisTrace front end. Plain JS, no build step.
 *
 * The server owns every judgement: each change is sent to the API, and the note that
 * comes back (with its evidence summary) is what the page shows. Text is always
 * inserted as text, never as HTML. */
"use strict";

const LABELS = [
  { value: "supported", name: "Supported" },
  { value: "mixed", name: "Mixed" },
  { value: "unverified", name: "Unverified" },
];
const VERDICT_TAGS = {
  empty: "No assumptions",
  blocked: "Not ready",
  needs_sources: "Needs sources",
  contested: "Contested",
  supported: "Supported",
};

const state = { notes: [], note: null };
const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

/* Where requests go: the FastAPI server when one answers, otherwise the in-browser engine
   (assets/engine.js), which applies the same rules and saves notes on this device only. */
let local = null;

async function chooseBackend() {
  // GitHub Pages never has the server, so skip the probe (and its 404) there.
  if (!location.hostname.endsWith("github.io")) {
    try {
      const response = await fetch("api/notes", { headers: { Accept: "application/json" } });
      const type = response.headers.get("content-type") || "";
      if (response.ok && type.includes("application/json")) return;
    } catch {
      /* no server: fall through to the browser engine */
    }
  }
  local = window.ThesisEngine.createEngine(window.ThesisEngine.browserStorage());
  $("#mode").textContent =
    "Running in your browser: notes are saved on this device only and are not sent anywhere.";
}

async function api(method, path, body) {
  if (local) {
    // Round-trip through JSON so the page never shares objects with the engine's state.
    const result = local.request(method, path, body ? JSON.parse(JSON.stringify(body)) : undefined);
    return result === null ? null : JSON.parse(JSON.stringify(result));
  }
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.error?.message || `Request failed (${response.status})`);
  }
  return data;
}

function autosize(area) {
  area.style.height = "auto";
  area.style.height = `${area.scrollHeight + 2}px`;
}

/* ---------- Note list ---------- */

async function loadNotes() {
  state.notes = await api("GET", "api/notes");
  renderNoteList();
}

function renderNoteList() {
  const list = $("#note-list");
  list.replaceChildren(
    ...state.notes.map((item) =>
      el(
        "li",
        {},
        el(
          "button",
          {
            type: "button",
            class: "note-link",
            "aria-current": state.note?.id === item.id ? "true" : "false",
            onclick: () => openNote(item.id),
          },
          item.question,
          el("span", {
            class: "note-meta",
            text: `${VERDICT_TAGS[item.verdict]} · ${item.total} assumption${item.total === 1 ? "" : "s"}`,
          }),
        ),
      ),
    ),
  );
  if (!state.notes.length) {
    list.append(el("li", { class: "note-meta", text: "No notes yet." }));
  }
}

function syncListEntry() {
  const note = state.note;
  const entry = state.notes.find((item) => item.id === note.id);
  if (entry) {
    entry.question = note.question;
    entry.verdict = note.summary.verdict;
    entry.total = note.summary.total;
  }
  renderNoteList();
}

/* ---------- Note ---------- */

async function openNote(id) {
  state.note = await api("GET", `api/notes/${encodeURIComponent(id)}`);
  history.replaceState(null, "", `#${id}`);
  renderNote();
  renderSummary();
  renderNoteList();
}

function applyNote(note) {
  state.note = note;
  renderSummary();
  syncListEntry();
}

function noteField(label, key, rows, placeholder) {
  const area = el("textarea", { rows, maxlength: 2000, placeholder });
  area.value = state.note[key];
  area.addEventListener("change", () => saveNote({ [key]: area.value }, area));
  return el("label", { class: "field" }, el("span", { text: label }), area);
}

async function saveNote(changes, input) {
  try {
    applyNote(await api("PATCH", `api/notes/${state.note.id}`, changes));
  } catch (error) {
    input.setCustomValidity(error.message);
    input.reportValidity();
    input.setCustomValidity("");
  }
}

function renderNote() {
  const main = $("#note");
  const note = state.note;
  if (!note) {
    main.replaceChildren(
      el("p", {
        class: "empty-state",
        text: "Pick a note, or start one with the question you are trying to answer.",
      }),
    );
    $("#summary").hidden = true;
    return;
  }

  const question = el("textarea", {
    class: "question",
    rows: 1,
    maxlength: 300,
    "aria-label": "Research question",
  });
  question.value = note.question;
  question.addEventListener("input", () => autosize(question));
  question.addEventListener("change", () => {
    if (!question.value.trim()) {
      question.value = state.note.question;
      autosize(question);
      return;
    }
    saveNote({ question: question.value }, question);
  });

  const list = el("ol", { class: "assumptions", id: "assumptions" });
  for (const item of note.assumptions) list.append(assumptionCard(item));

  main.replaceChildren(
    el("p", { class: "eyebrow", text: "Research note" }),
    question,
    el(
      "div",
      { class: "note-fields" },
      noteField("Context", "context", 2, "What a reviewer needs to know first"),
      noteField("Tentative conclusion", "conclusion", 2, "What you currently believe, and on what terms"),
    ),
    el(
      "div",
      { class: "section-head" },
      el("h2", { text: "Assumptions" }),
      el("p", { text: "What has to be true for the conclusion to hold" }),
    ),
    list,
    addForm(),
    el(
      "div",
      { class: "note-actions" },
      el("button", { type: "button", class: "button quiet", onclick: deleteNote, text: "Delete note" }),
    ),
  );
  $("#summary").hidden = false;
  requestAnimationFrame(() => main.querySelectorAll("textarea.question, textarea.statement").forEach(autosize));
}

async function deleteNote() {
  if (!confirm("Delete this note and all of its assumptions?")) return;
  await api("DELETE", `api/notes/${state.note.id}`);
  state.note = null;
  history.replaceState(null, "", location.pathname);
  await loadNotes();
  renderNote();
}

/* ---------- Assumptions ---------- */

function assumptionCard(item) {
  const card = $("#assumption-template").content.firstElementChild.cloneNode(true);
  const idBase = `${item.id}`;
  card.id = item.id;
  card.dataset.evidence = item.evidence;
  card.classList.toggle("needs-source", item.evidence === "unverified" && item.critical);

  const statement = $(".statement", card);
  statement.id = `${idBase}-statement`;
  $(".assumption-head label", card).htmlFor = statement.id;
  statement.value = item.statement;
  statement.addEventListener("input", () => autosize(statement));
  statement.addEventListener("change", () => {
    if (!statement.value.trim()) {
      statement.value = current(item.id).statement;
      return showCardError(card, "An assumption needs some text. Use Remove to delete it.");
    }
    patchAssumption(card, { statement: statement.value });
  });

  const fieldset = $(".labels", card);
  for (const label of LABELS) {
    const radio = el("input", { type: "radio", name: `${idBase}-evidence`, value: label.value });
    radio.checked = item.evidence === label.value;
    radio.addEventListener("change", () => changeEvidence(card, label.value));
    fieldset.append(el("label", { class: "pill" }, radio, el("span", { text: label.name })));
  }

  const source = $(".source", card);
  source.value = item.source ?? "";
  source.addEventListener("change", () => {
    const value = source.value.trim();
    if (!value && current(item.id).evidence !== "unverified") {
      source.value = current(item.id).source ?? "";
      return showCardError(card, "Supported or mixed evidence needs a source. Mark it unverified first to clear it.");
    }
    patchAssumption(card, { source: value || null });
  });

  const rationale = $(".rationale", card);
  rationale.value = item.rationale;
  rationale.addEventListener("change", () => patchAssumption(card, { rationale: rationale.value }));

  const critical = $(".critical-box", card);
  critical.checked = item.critical;
  critical.addEventListener("change", () => patchAssumption(card, { critical: critical.checked }));

  $(".remove", card).addEventListener("click", () => removeAssumption(card));
  return card;
}

function current(id) {
  return state.note.assumptions.find((item) => item.id === id);
}

function showCardError(card, message) {
  $(".card-error", card).textContent = message;
}

function refreshCard(card) {
  const item = current(card.id);
  card.dataset.evidence = item.evidence;
  card.classList.toggle("needs-source", item.evidence === "unverified" && item.critical);
  for (const radio of card.querySelectorAll(".labels input")) radio.checked = radio.value === item.evidence;
}

async function patchAssumption(card, changes) {
  showCardError(card, "");
  try {
    applyNote(await api("PATCH", `api/notes/${state.note.id}/assumptions/${card.id}`, changes));
    refreshCard(card);
    return true;
  } catch (error) {
    refreshCard(card);
    showCardError(card, error.message);
    return false;
  }
}

async function changeEvidence(card, evidence) {
  const source = $(".source", card);
  const typed = source.value.trim();
  const changes = { evidence };
  // A source typed but not yet saved travels with the new label.
  if (typed && typed !== (current(card.id).source ?? "")) changes.source = typed;
  if (evidence !== "unverified" && !typed) {
    refreshCard(card);
    showCardError(card, `Add a source before marking this ${evidence}.`);
    source.focus();
    return;
  }
  await patchAssumption(card, changes);
}

async function removeAssumption(card) {
  try {
    applyNote(await api("DELETE", `api/notes/${state.note.id}/assumptions/${card.id}`));
    card.remove();
  } catch (error) {
    showCardError(card, error.message);
  }
}

function addForm() {
  const statement = el("textarea", {
    id: "add-statement",
    rows: 2,
    maxlength: 500,
    required: true,
    placeholder: "e.g. Free cash flow stays above $120M a year",
  });
  const source = el("input", {
    id: "add-source",
    type: "text",
    maxlength: 500,
    placeholder: "Optional: filing, page, dataset",
  });
  const critical = el("input", { type: "checkbox", class: "critical-box" });
  const labels = el("fieldset", { class: "labels" }, el("legend", { class: "visually-hidden", text: "Evidence" }));
  for (const label of LABELS) {
    const radio = el("input", { type: "radio", name: "add-evidence", value: label.value });
    // defaultChecked, not just checked: form.reset() after each add returns to this.
    radio.checked = radio.defaultChecked = label.value === "unverified";
    labels.append(el("label", { class: "pill" }, radio, el("span", { text: label.name })));
  }
  const error = el("p", { class: "form-error", role: "alert" });

  const form = el(
    "form",
    { class: "add" },
    el("h3", { text: "Add an assumption" }),
    el("label", { class: "field" }, el("span", { text: "Assumption" }), statement),
    labels,
    el("label", { class: "field" }, el("span", { text: "Source" }), source),
    el(
      "div",
      { class: "add-row" },
      el("label", { class: "critical" }, critical, el("span", { text: "Load-bearing" })),
      el("button", { type: "submit", class: "button", text: "Add assumption" }),
    ),
    error,
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const evidence = form.querySelector("input[name=add-evidence]:checked")?.value ?? "unverified";
    try {
      const note = await api("POST", `api/notes/${state.note.id}/assumptions`, {
        statement: statement.value,
        evidence,
        source: source.value.trim() || null,
        critical: critical.checked,
      });
      applyNote(note);
      const added = note.assumptions[note.assumptions.length - 1];
      const card = assumptionCard(added);
      $("#assumptions").append(card);
      autosize($(".statement", card));
      card.classList.add("flash");
      form.reset();
      statement.focus();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  return form;
}

/* ---------- Summary ---------- */

function renderSummary() {
  const note = state.note;
  if (!note) return;
  const summary = note.summary;

  $("#verdict").replaceChildren(
    el("span", { class: "verdict-tag", "data-verdict": summary.verdict, text: VERDICT_TAGS[summary.verdict] }),
    el("br"),
    summary.headline,
  );

  const bar = $("#bar");
  bar.replaceChildren(
    ...LABELS.map((label) => {
      const span = el("span", { class: label.value });
      span.style.width = `${summary.shares[label.value]}%`;
      return span;
    }),
  );
  bar.setAttribute(
    "aria-label",
    LABELS.map((l) => `${l.name} ${summary.shares[l.value]}%`).join(", "),
  );

  $("#legend").replaceChildren(
    ...LABELS.map((label) =>
      el(
        "div",
        { class: label.value },
        el("dt", { text: label.name }),
        el("dd", {}, String(summary.counts[label.value]), el("small", { text: `${summary.shares[label.value]}%` })),
      ),
    ),
  );

  const byId = new Map(note.assumptions.map((item) => [item.id, item]));
  const empty = {
    needs_source: "Nothing waiting on a source.",
    uncertain: "No mixed evidence.",
    proven: "Nothing proven yet.",
  };
  for (const bucket of ["needs_source", "uncertain", "proven"]) {
    const list = $(`[data-bucket="${bucket}"] ol`);
    const ids = summary[bucket];
    list.replaceChildren(
      ...(ids.length
        ? ids.map((id) => {
            const item = byId.get(id);
            return el(
              "li",
              {},
              el("a", { href: `#${id}`, onclick: (event) => focusCard(event, id), text: item.statement }),
              item.critical ? el("span", { class: "tag-critical", text: "Load-bearing" }) : null,
            );
          })
        : [el("li", { class: "none", text: empty[bucket] })]),
    );
  }
}

function focusCard(event, id) {
  event.preventDefault();
  const card = document.getElementById(id);
  if (!card) return;
  const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  card.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  card.classList.remove("flash");
  void card.offsetWidth;
  card.classList.add("flash");
  $(".statement", card).focus({ preventScroll: true });
}

/* ---------- Start ---------- */

$("#new-note").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#new-question");
  try {
    const note = await api("POST", "api/notes", { question: input.value });
    input.value = "";
    await loadNotes();
    await openNote(note.id);
    $("#add-statement").focus();
  } catch (error) {
    input.setCustomValidity(error.message);
    input.reportValidity();
    input.setCustomValidity("");
  }
});

(async () => {
  await chooseBackend();
  await loadNotes();
  const wanted = location.hash.slice(1);
  const first = state.notes.find((n) => n.id === wanted) ?? state.notes[0];
  if (first) await openNote(first.id);
})();
