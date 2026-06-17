"use strict";

// ---------------------------------------------------------------------------
//  Tiny helpers
// ---------------------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return node;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return null;
  const ct = res.headers.get("Content-Type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || ("HTTP " + res.status));
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 2200);
}

// ---------------------------------------------------------------------------
//  Global state
// ---------------------------------------------------------------------------
const state = {
  meta: null,
  projects: [],
  pid: null,
  project: null,
  tab: "dashboard",
};

function currentTab() { return state.tab; }

// ---------------------------------------------------------------------------
//  Modal
// ---------------------------------------------------------------------------
function openModal(title, bodyNodes, { okLabel = "Save", onOk = null, danger = false } = {}) {
  closeModal();
  const okBtn = el("button", { class: danger ? "btn-danger" : "btn-primary" }, okLabel);
  const backdrop = el("div", { class: "modal-backdrop", onclick: (e) => { if (e.target === backdrop) closeModal(); } },
    el("div", { class: "modal" },
      el("h2", {}, title),
      ...(Array.isArray(bodyNodes) ? bodyNodes : [bodyNodes]),
      el("div", { class: "modal-actions" },
        el("button", { class: "btn-ghost", onclick: closeModal }, "Cancel"),
        okBtn)));
  if (onOk) okBtn.addEventListener("click", () => onOk(closeModal));
  else okBtn.remove();
  $("#modal-root").append(backdrop);
  const firstInput = backdrop.querySelector("input, textarea, select");
  if (firstInput) firstInput.focus();
}
function closeModal() { $("#modal-root").innerHTML = ""; }

function confirmModal(title, message, onYes, { okLabel = "Delete", danger = true } = {}) {
  openModal(title, el("p", { class: "muted" }, message), {
    okLabel, danger, onOk: (close) => { close(); onYes(); },
  });
}

function field(labelText, inputNode) {
  return el("div", { class: "field" }, el("label", {}, labelText), inputNode);
}

// ---------------------------------------------------------------------------
//  Boot
// ---------------------------------------------------------------------------
async function boot() {
  bindChrome();
  try {
    state.meta = await api("/meta");
    await loadProjects();
  } catch (e) {
    $("#view").append(el("div", { class: "empty" }, "Could not reach the server: " + e.message));
    return;
  }
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

function bindChrome() {
  $("#tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t === btn);
    state.tab = btn.dataset.tab;
    render();
  });
  $("#project-select").addEventListener("change", (e) => selectProject(Number(e.target.value)));
  $("#project-menu-btn").addEventListener("click", projectMenu);
}

async function loadProjects() {
  state.projects = await api("/projects");
  const sel = $("#project-select");
  sel.innerHTML = "";
  for (const p of state.projects) sel.append(el("option", { value: p.id }, p.name));
  if (state.projects.length === 0) {
    state.pid = null;
    state.project = null;
    promptCreateProject(true);
    render();
    return;
  }
  if (!state.projects.find((p) => p.id === state.pid)) state.pid = state.projects[0].id;
  sel.value = state.pid;
  state.project = await api("/projects/" + state.pid);
  render();
}

async function selectProject(pid) {
  state.pid = pid;
  state.project = await api("/projects/" + pid);
  render();
}

function projectMenu() {
  const body = el("div", { class: "stack" },
    el("button", { class: "btn-block", onclick: () => { closeModal(); promptCreateProject(); } }, "New project"),
    state.project && el("button", { class: "btn-block", onclick: () => { closeModal(); renameProject(); } }, "Rename project"),
    state.project && el("button", { class: "btn-block btn-danger", onclick: () => { closeModal(); deleteProject(); } }, "Delete project"));
  openModal("Projects", body);
}

function promptCreateProject(first = false) {
  const input = el("input", { type: "text", placeholder: "e.g. The Effect of X on Y" });
  openModal(first ? "Create your first project" : "New project",
    field("Project name", input), {
      okLabel: "Create",
      onOk: async (close) => {
        const name = input.value.trim();
        if (!name) return;
        const p = await api("/projects", { method: "POST", body: { name } });
        close();
        state.pid = p.id;
        await loadProjects();
        state.pid = p.id; $("#project-select").value = p.id;
        state.project = p;
        toast("Project created");
        render();
      },
    });
}

function renameProject() {
  const input = el("input", { type: "text", value: state.project.name });
  openModal("Rename project", field("Project name", input), {
    okLabel: "Save",
    onOk: async (close) => {
      const name = input.value.trim();
      if (!name) return;
      await api("/projects/" + state.pid, { method: "PATCH", body: { name } });
      close();
      await loadProjects();
      toast("Renamed");
    },
  });
}

function deleteProject() {
  confirmModal("Delete project",
    `Delete "${state.project.name}" and all its sources, timeline, and sections? This cannot be undone.`,
    async () => {
      await api("/projects/" + state.pid, { method: "DELETE" });
      state.pid = null;
      await loadProjects();
      toast("Project deleted");
    });
}

// ---------------------------------------------------------------------------
//  Render dispatch
// ---------------------------------------------------------------------------
function render() {
  const view = $("#view");
  view.innerHTML = "";
  if (!state.project) {
    view.append(el("div", { class: "empty" }, "No project yet. Use the ⋮ menu to create one."));
    return;
  }
  ({ dashboard: renderDashboard, sources: renderSources,
     timeline: renderTimeline, sections: renderSections }[currentTab()])(view);
}

// ---------------------------------------------------------------------------
//  Dashboard
// ---------------------------------------------------------------------------
async function renderDashboard(view) {
  const p = state.project;
  const [sources, checkpoints, sections] = await Promise.all([
    api(`/projects/${p.id}/sources`),
    api(`/projects/${p.id}/checkpoints`),
    api(`/projects/${p.id}/sections`),
  ]);

  // Research question + style
  const rq = el("textarea", { placeholder: "What is your research question?" }, p.research_question);
  rq.value = p.research_question || "";
  const saveRq = el("button", { class: "btn-sm", onclick: async () => {
    await api("/projects/" + p.id, { method: "PATCH", body: { research_question: rq.value } });
    state.project.research_question = rq.value;
    toast("Saved");
  } }, "Save");

  const styleSeg = el("div", { class: "seg" },
    ...state.meta.styles.map((s) => el("button", {
      class: p.citation_style === s ? "on" : "",
      onclick: async () => {
        await api("/projects/" + p.id, { method: "PATCH", body: { citation_style: s } });
        state.project.citation_style = s;
        render();
        toast("Citation style: " + s);
      },
    }, s)));

  view.append(el("div", { class: "card" },
    el("h2", {}, "Research question"),
    rq,
    el("div", { class: "row", style: "margin-top:8px" },
      el("div", { class: "spacer" }), saveRq),
    el("div", { class: "row wrap", style: "margin-top:14px" },
      el("label", { style: "margin:0" }, "Citation style"), styleSeg)));

  // Word count summary
  const cur = sections.reduce((a, s) => a + (s.current_words || 0), 0);
  const tgt = sections.reduce((a, s) => a + (s.target_words || 0), 0);
  const pct = tgt ? Math.min(100, Math.round((cur / tgt) * 100)) : 0;
  let cls = "warn";
  if (cur >= p.word_min && cur <= p.word_max) cls = "good";
  else if (cur > p.word_max) cls = "bad";
  view.append(el("div", { class: "card" },
    el("h2", {}, "Word count"),
    el("div", { class: "row" },
      el("strong", {}, cur.toLocaleString()),
      el("span", { class: "muted" }, ` / target ${tgt.toLocaleString()} (range ${p.word_min.toLocaleString()}–${p.word_max.toLocaleString()})`)),
    el("div", { class: "bar " + cls, style: "margin-top:8px" }, el("span", { style: `width:${pct}%` }))));

  // Timeline summary
  const done = checkpoints.filter((c) => c.done).length;
  const upcoming = checkpoints
    .filter((c) => !c.done && c.target_date)
    .sort((a, b) => a.target_date.localeCompare(b.target_date))[0];
  view.append(el("div", { class: "card" },
    el("h2", {}, "Progress"),
    el("div", {}, `Sources: ${sources.length}`),
    el("div", {}, `Checkpoints done: ${done} / ${checkpoints.length}`),
    upcoming
      ? el("div", {}, "Next: ", el("strong", {}, upcoming.name), ` — ${upcoming.target_date} (${daysLeftLabel(upcoming.target_date)})`)
      : el("div", { class: "muted" }, "No upcoming dated checkpoints.")));
}

function daysLeftLabel(iso) {
  const today = new Date(state.meta.today + "T00:00:00");
  const d = new Date(iso + "T00:00:00");
  const days = Math.round((d - today) / 86400000);
  if (days < 0) return `${-days}d overdue`;
  if (days === 0) return "today";
  return `${days}d left`;
}

// ---------------------------------------------------------------------------
//  Sources
// ---------------------------------------------------------------------------
async function renderSources(view) {
  const p = state.project;
  const sources = await api(`/projects/${p.id}/sources`);

  view.append(el("div", { class: "row wrap", style: "margin-bottom:12px" },
    el("button", { class: "btn-primary", onclick: () => sourceForm() }, "+ Add source"),
    el("button", { onclick: importBibtex }, "Import BibTeX"),
    el("button", { onclick: () => download(`/api/projects/${p.id}/sources/export.bib`) }, "Export .bib"),
    el("button", { onclick: () => download(`/api/projects/${p.id}/citations.pdf`) }, "PDF")));

  if (sources.length === 0) {
    view.append(el("div", { class: "empty" }, "No sources yet. Add one or import a BibTeX file."));
    return;
  }

  for (const s of sources) {
    view.append(el("div", { class: "item" },
      el("div", { class: "row wrap", style: "margin-bottom:6px" },
        el("span", { class: "chip" }, s.entry_type),
        s.cite_key ? el("span", { class: "chip" }, s.cite_key) : null),
      el("div", { class: "citation", html: s.citation_html }),
      el("div", { class: "small muted", style: "margin-top:6px" }, "In-text: " + s.intext),
      el("div", { class: "item-actions" },
        el("button", { class: "btn-sm", onclick: () => copyText(s.citation_text) }, "Copy"),
        el("button", { class: "btn-sm", onclick: () => copyText(s.intext) }, "Copy in-text"),
        el("button", { class: "btn-sm", onclick: () => sourceForm(s) }, "Edit"),
        el("button", { class: "btn-sm btn-danger", onclick: () => deleteSource(s) }, "Delete"))));
  }
}

function sourceForm(src = null) {
  const typeSel = el("select", {},
    ...state.meta.entry_types.map((t) => el("option", { value: t, selected: src && src.entry_type === t }, t)));
  if (!src) typeSel.value = "article";
  const keyInput = el("input", { type: "text", value: src ? src.cite_key || "" : "", placeholder: "e.g. smith2020" });
  const fieldInputs = {};
  const fieldNodes = state.meta.editor_fields.map(({ label, key }) => {
    const val = src && src.fields ? src.fields[key] || "" : "";
    const input = key === "url" || key === "note"
      ? el("textarea", {}, val)
      : el("input", { type: "text", value: val });
    if (input.tagName === "TEXTAREA") input.value = val;
    fieldInputs[key] = input;
    return field(label, input);
  });

  openModal(src ? "Edit source" : "Add source", [
    field("Type", typeSel),
    field("Cite key", keyInput),
    ...fieldNodes,
  ], {
    okLabel: src ? "Save" : "Add",
    onOk: async (close) => {
      const fields = {};
      for (const [k, input] of Object.entries(fieldInputs)) {
        const v = input.value.trim();
        if (v) fields[k] = v;
      }
      const body = { cite_key: keyInput.value.trim(), entry_type: typeSel.value, fields };
      if (src) await api("/sources/" + src.id, { method: "PATCH", body });
      else await api(`/projects/${state.pid}/sources`, { method: "POST", body });
      close();
      toast(src ? "Source saved" : "Source added");
      render();
    },
  });
}

function deleteSource(s) {
  confirmModal("Delete source", `Delete "${s.cite_key || s.citation_text.slice(0, 40)}"?`, async () => {
    await api("/sources/" + s.id, { method: "DELETE" });
    toast("Deleted");
    render();
  });
}

function importBibtex() {
  const ta = el("textarea", { placeholder: "Paste BibTeX entries here…", style: "min-height:160px" });
  const file = el("input", { type: "file", accept: ".bib,.txt,text/plain" });
  file.addEventListener("change", async () => {
    if (file.files[0]) ta.value = await file.files[0].text();
  });
  openModal("Import BibTeX", [field("Upload a .bib file", file), field("…or paste", ta)], {
    okLabel: "Import",
    onOk: async (close) => {
      const text = ta.value.trim();
      if (!text) return;
      const res = await api(`/projects/${state.pid}/sources/import`, { method: "POST", body: { bibtex: text } });
      close();
      toast(`Imported ${res.imported} source(s)`);
      render();
    },
  });
}

// ---------------------------------------------------------------------------
//  Timeline
// ---------------------------------------------------------------------------
async function renderTimeline(view) {
  const p = state.project;
  const cps = await api(`/projects/${p.id}/checkpoints`);

  view.append(el("div", { class: "row wrap", style: "margin-bottom:12px" },
    el("button", { class: "btn-primary", onclick: () => checkpointForm() }, "+ Add checkpoint"),
    el("button", { onclick: () => download(`/api/projects/${p.id}/calendar.ics`) }, "Export .ics")));

  if (cps.length === 0) {
    view.append(el("div", { class: "empty" }, "No checkpoints yet."));
    return;
  }

  for (const c of cps) {
    const overdue = !c.done && c.target_date && c.target_date < state.meta.today;
    const cb = el("input", { type: "checkbox" });
    cb.checked = !!c.done;
    cb.addEventListener("change", async () => {
      await api("/checkpoints/" + c.id, { method: "PATCH", body: { done: cb.checked } });
      render();
    });
    view.append(el("div", { class: "item " + (c.done ? "done" : "") },
      el("div", { class: "check-row" },
        cb,
        el("div", { style: "flex:1" },
          el("div", { class: "cp-name", style: "font-weight:500" }, c.name),
          el("div", { class: "small " + (overdue ? "overdue" : "muted") },
            c.target_date ? `${c.target_date}${c.done ? "" : " — " + daysLeftLabel(c.target_date)}` : "No date")),
        el("button", { class: "icon-btn", onclick: () => checkpointForm(c) }, "✎"),
        el("button", { class: "icon-btn", onclick: () => deleteCheckpoint(c) }, "🗑"))));
  }
}

function checkpointForm(cp = null) {
  const name = el("input", { type: "text", value: cp ? cp.name : "" });
  const date = el("input", { type: "date", value: cp && cp.target_date ? cp.target_date : "" });
  openModal(cp ? "Edit checkpoint" : "Add checkpoint",
    [field("Name", name), field("Target date", date)], {
      okLabel: cp ? "Save" : "Add",
      onOk: async (close) => {
        const body = { name: name.value.trim(), target_date: date.value || null };
        if (!body.name) return;
        if (cp) await api("/checkpoints/" + cp.id, { method: "PATCH", body });
        else await api(`/projects/${state.pid}/checkpoints`, { method: "POST", body });
        close();
        toast(cp ? "Saved" : "Added");
        render();
      },
    });
}

function deleteCheckpoint(c) {
  confirmModal("Delete checkpoint", `Delete "${c.name}"?`, async () => {
    await api("/checkpoints/" + c.id, { method: "DELETE" });
    toast("Deleted");
    render();
  });
}

// ---------------------------------------------------------------------------
//  Sections
// ---------------------------------------------------------------------------
async function renderSections(view) {
  const p = state.project;
  const sections = await api(`/projects/${p.id}/sections`);

  const cur = sections.reduce((a, s) => a + (s.current_words || 0), 0);
  const tgt = sections.reduce((a, s) => a + (s.target_words || 0), 0);
  view.append(el("div", { class: "card" },
    el("div", { class: "row" },
      el("strong", {}, "Total: " + cur.toLocaleString()),
      el("span", { class: "muted" }, ` / ${tgt.toLocaleString()} words`),
      el("div", { class: "spacer" }),
      el("button", { class: "btn-sm btn-ghost", onclick: resetSections }, "Reset to defaults"))));

  for (const s of sections) {
    const curInput = el("input", { type: "number", min: "0", value: s.current_words, inputmode: "numeric" });
    const tgtInput = el("input", { type: "number", min: "0", value: s.target_words, inputmode: "numeric" });
    const notes = el("textarea", { placeholder: "Notes…" });
    notes.value = s.notes || "";
    const pct = s.target_words ? Math.min(100, Math.round((s.current_words / s.target_words) * 100)) : 0;
    const save = async () => {
      await api("/sections/" + s.id, { method: "PATCH", body: {
        current_words: Number(curInput.value) || 0,
        target_words: Number(tgtInput.value) || 0,
        notes: notes.value,
      } });
      toast("Saved");
      render();
    };
    view.append(el("div", { class: "item" },
      el("div", { style: "font-weight:600;margin-bottom:8px" }, s.name),
      el("div", { class: "bar", style: "margin-bottom:10px" }, el("span", { style: `width:${pct}%` })),
      el("div", { class: "row" },
        el("div", { style: "flex:1" }, el("label", {}, "Current"), curInput),
        el("div", { style: "flex:1" }, el("label", {}, "Target"), tgtInput)),
      field("Notes", notes),
      el("div", { class: "row" }, el("div", { class: "spacer" }),
        el("button", { class: "btn-sm btn-primary", onclick: save }, "Save"))));
  }
}

function resetSections() {
  confirmModal("Reset sections",
    "Restore the 7 required sections to default targets, clear word counts and notes?",
    async () => {
      await api(`/projects/${state.pid}/sections/reset`, { method: "POST" });
      toast("Sections reset");
      render();
    }, { okLabel: "Reset", danger: true });
}

// ---------------------------------------------------------------------------
//  Misc
// ---------------------------------------------------------------------------
function download(url) {
  const a = el("a", { href: url, download: "" });
  document.body.append(a);
  a.click();
  a.remove();
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied");
  } catch {
    // Fallback for non-secure contexts (plain http on LAN).
    const ta = el("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    toast("Copied");
  }
}

boot();
