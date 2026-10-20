// Library tab: every model with its picture, last step and timings; open, copy, remove and put
// back (never erased); and "Make several at once" (the batch queue). app.js passes in what it owns.
const $ = (id) => document.getElementById(id);
const STEP_WORDS = { generate: "Make", clean: "Clean up", skeleton: "Skeleton", animate: "Animate" };
const TYPE_WORDS = { humanoid: "Humanoid", monster: "Monster", animal: "Animal" };
let ctx = null;          // { api, post, open, generator, types, drawNote }
let batchId = null;
let timer = null;

function secs(s) { return s >= 90 ? `${Math.round(s / 6) / 10} min` : `${Math.round(s)} s`; }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function when(t) {
  return new Date(t * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
function timings(t) {
  const parts = [];
  if (t.draw !== undefined) parts.push(`Picture ${secs(t.draw)}`);
  if (t.generate !== undefined) parts.push(`Make ${secs(t.generate)}`);
  if (t.clean !== undefined) parts.push(`Clean up ${secs(t.clean)}`);
  if (t.skeleton !== undefined) parts.push(`Skeleton ${secs(t.skeleton)}`);
  return parts.length ? "Took: " + parts.join(", ") : "";
}

function card(a, trashed) {
  const c = el("div", "card");
  const th = el("div", "thumb");
  if (a.thumb) {
    const img = el("img");
    img.alt = "";
    img.loading = "lazy";
    img.src = `/api/assets/${a.id}/files/generate/input.png`;
    th.append(img);
  } else th.textContent = "No picture yet";
  const body = el("div", "cbody");
  body.append(el("div", "ctitle", a.prompt || `${TYPE_WORDS[a.type] || "Model"} from a picture`));
  body.append(el("div", "cmeta", `${TYPE_WORDS[a.type] || a.type} · ${when(a.created)}`));
  const status = a.busy ? "Being made now..."
    : a.failed ? "Did not finish. Open it and press Redo."
    : a.reached ? `Last step: ${STEP_WORDS[a.reached] || a.reached}` : "Not made yet";
  body.append(el("div", "cstate" + (a.failed ? " bad" : a.busy ? " busy" : ""), status));
  const t = timings(a.timings || {});
  if (t) body.append(el("div", "cmeta", t));
  const btns = el("div", "cbtns");
  const add = (label, fn, cls = "secondary") => {
    const b = el("button", cls + " small", label);
    b.type = "button";
    b.onclick = fn;
    btns.append(b);
    return b;
  };
  if (trashed) add("Put back", () => act(`/api/assets/${a.id}/restore`));
  else {
    add("Open", () => ctx.open(a.id), "primary").disabled = !a.thumb && !!a.busy;
    if (a.reached === "skeleton") add("Open at Make", () => ctx.open(a.id, "generate"));
    const idle = !a.busy;
    add("Copy", () => act(`/api/assets/${a.id}/duplicate`)).disabled = !idle;
    add("Remove", () => act(`/api/assets/${a.id}/trash`)).disabled = !idle;
  }
  body.append(btns);
  c.append(th, body);
  return c;
}

async function act(path) {
  try { await ctx.post(path, {}); } catch (e) { $("batch-note").textContent = e.message; }
  refresh();
}

export async function refresh() {
  const [live, gone] = await Promise.all([ctx.api("/api/library"), ctx.api("/api/library?trash=1")]);
  const cards = $("cards");
  cards.replaceChildren(...live.map((a) => card(a, false)));
  $("lib-empty").classList.toggle("hidden", live.length > 0);
  $("trash-box").classList.toggle("hidden", gone.length === 0);
  $("trash-sum").textContent = `Removed models (${gone.length})`;
  $("trash-cards").replaceChildren(...gone.map((a) => card(a, true)));
  return live.some((a) => a.busy);
}

// batch rows
function addRow(prompt = "") {
  const row = el("div", "brow");
  const inp = el("input");
  inp.type = "text";
  inp.maxLength = 600;
  inp.placeholder = "A few words, like: a tired knight";
  inp.value = prompt;
  inp.setAttribute("aria-label", "Description");
  const sel = el("select");
  sel.setAttribute("aria-label", "What is it");
  ctx.types().forEach((t) => sel.append(new Option(t.label, t.id)));
  const rm = el("button", "secondary small", "Remove this line");
  rm.type = "button";
  rm.onclick = () => { row.remove(); renderBatchButtons(); };
  row.append(inp, sel, rm);
  $("batch-rows").append(row);
  renderBatchButtons();
}
function renderBatchButtons() {
  const n = $("batch-rows").children.length;
  $("batch-rows").querySelectorAll("button").forEach((b) => b.classList.toggle("hidden", n < 2));
  $("batch-add").disabled = n >= 20;
}

function batchLine(it) {
  const line = el("div", "bitem " + it.state);
  let txt;
  if (it.state === "done") txt = "Done";
  else if (it.state === "failed") txt = it.error || "Did not finish";
  else if (it.state === "running") txt = `${it.message}  ${Math.floor(it.elapsed_s)} s`;
  else txt = it.ahead > 1 ? `Waiting, ${it.ahead} ahead of it` : "Next in line";
  line.append(el("b", "", it.prompt), el("span", "", txt));
  return line;
}
async function pollBatch() {
  if (!batchId) return;
  const b = await ctx.api(`/api/batch/${batchId}`);
  const list = $("batch-list");
  list.replaceChildren(el("div", "bhead", b.finished
    ? `All ${b.items.length} finished (${b.done} made)`
    : `${b.done} of ${b.items.length} made`), ...b.items.map(batchLine));
  if (b.finished) batchId = null;
}

async function goBatch() {
  const items = [...$("batch-rows").children].map((r) => ({
    prompt: r.querySelector("input").value.trim(), type: r.querySelector("select").value }))
    .filter((i) => i.prompt);
  const note = $("batch-note");
  note.textContent = "";
  if (!items.length) { note.textContent = "Type a description first."; return; }
  try {
    const b = await ctx.post("/api/batch", { items, generator: ctx.generator() });
    batchId = b.id;
    $("batch-rows").replaceChildren();
    addRow();
    await pollBatch();
    tick();
  } catch (e) { note.textContent = e.message; }
}

// While the tab is open, look again every 2 s if anything is being made.
async function tick() {
  clearTimeout(timer);
  if (!document.body.classList.contains("lib")) return;
  let busy = false;
  try { busy = await refresh(); await pollBatch(); } catch { /* try again next time */ }
  if (busy || batchId) timer = setTimeout(tick, 2000);
}

export function show() { tick(); }
export function hide() { clearTimeout(timer); }

export function initLibrary(c) {
  ctx = c;
  addRow();
  $("batch-add").onclick = () => addRow();
  $("batch-go").onclick = goBatch;
  const note = c.drawNote();
  $("batch-go").disabled = !!note;
  $("batch-note").textContent = note;
}
