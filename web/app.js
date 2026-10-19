import { Viewer } from "./viewer.js";

const $ = (id) => document.getElementById(id);
const state = {
  file: null, type: null, generator: null, asset: null,
  busy: false, done: false, step: 1, menu: null,
};
let viewer = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch { /* not json */ }
  if (!r.ok) {
    throw new Error((body && body.detail) || "Something went wrong. Try again.");
  }
  return body;
}

function showMsg(text, kind = "") {
  const m = $("viewer-msg");
  m.className = "viewer-msg " + kind;
  m.textContent = text;
  m.classList.toggle("hidden", !text);
}
function note(el, text, kind = "") {
  el.className = "note " + kind;
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

function render() {
  const onStep1 = state.step === 1;
  $("panel-1").classList.toggle("hidden", !onStep1);
  $("panel-2").classList.toggle("hidden", onStep1);
  document.querySelectorAll("#steps li").forEach((li) => {
    const n = Number(li.dataset.step);
    li.classList.toggle("current", n === state.step);
    li.classList.toggle("done", n < state.step);
  });
  const next = $("next"), redo = $("redo");
  if (onStep1) {
    if (state.done && !state.busy) {
      next.textContent = "Next: Clean up";
      next.disabled = false;
    } else {
      next.textContent = state.busy ? "Working..." : "Make 3D model";
      next.disabled = !state.file || state.busy;
    }
    redo.disabled = state.busy || !state.asset;
  } else {
    next.textContent = "Clean up the model";
    next.disabled = false;
    redo.disabled = true;
  }
  document.querySelectorAll("#types button, #generators .gen").forEach((b) => {
    b.disabled = state.busy;
  });
}

function buildMenu(menu) {
  state.menu = menu;
  const types = $("types");
  types.innerHTML = "";
  menu.types.forEach((t, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.value = t.id;
    b.textContent = t.label;
    b.onclick = () => selectType(t.id);
    types.append(b);
    if (i === 0) state.type = t.id;
  });
  const gens = $("generators");
  gens.innerHTML = "";
  menu.generators.forEach((g) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "gen";
    b.setAttribute("role", "radio");
    b.dataset.value = g.id;
    b.innerHTML = '<div class="name"></div><div class="blurb"></div><div class="facts"></div>';
    b.querySelector(".name").textContent = g.name;
    b.querySelector(".blurb").textContent = g.blurb;
    b.querySelector(".facts").textContent = `Takes ${g.typical_time}; ${g.vram}`;
    b.onclick = () => selectGenerator(g.id);
    gens.append(b);
    if (g.selected) state.generator = g.id;
  });
  selectType(state.type);
  selectGenerator(state.generator);
}
function selectType(id) {
  if (state.asset && id !== state.type) { state.asset = null; state.done = false; } // new type = new model
  state.type = id;
  document.querySelectorAll("#types button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.value === id)));
  render();
}
function selectGenerator(id) {
  state.generator = id;
  document.querySelectorAll("#generators .gen").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.value === id)));
}

function chooseFile(file) {
  if (!file) return;
  state.file = file;
  state.asset = null;
  state.done = false;
  $("preview").src = URL.createObjectURL(file);
  $("preview").classList.remove("hidden");
  $("drop").classList.add("has-image");
  $("drop-text").textContent = "Click to choose a different picture";
  note($("note"), "");
  render();
}

async function start() {
  if (state.busy || !state.file) return;
  state.busy = true;
  render();
  note($("note"), "");
  showMsg("Sending your picture...", "busy");
  try {
    if (!state.asset) {
      const fd = new FormData();
      fd.append("image", state.file);
      fd.append("type", state.type);
      state.asset = await api("/api/assets", { method: "POST", body: fd });
    }
    // a new seed every time: Redo keeps the picture and changes the roll of the dice
    const job = await api(`/api/assets/${state.asset.id}/generate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ generator: state.generator }),
    });
    await watch(job.id);
  } catch (e) {
    fail(e.message);
  }
}

async function watch(jobId) {
  for (;;) {
    const j = await api(`/api/jobs/${jobId}`);
    if (j.state === "done") return finish(j);
    if (j.state === "failed") return fail(j.error || j.message);
    let text = j.message;
    if (j.state === "queued" && j.ahead > 0) text = "Waiting for your turn";
    if (j.state === "running") text += `  ${Math.round(j.elapsed_s)} s`;
    showMsg(text, "busy");
    await new Promise((r) => setTimeout(r, 1000));
  }
}

async function finish(job) {
  const r = job.result;
  showMsg("Loading the model...", "busy");
  try {
    viewer = viewer || new Viewer($("viewer"));
    await viewer.load(`/api/assets/${job.asset_id}/files/generate/${r.mesh}?v=${job.id}`);
  } catch {
    return fail("The model was made but I could not show it. Press Redo to try again.");
  }
  showMsg("");
  $("viewer-hint").classList.remove("hidden");
  state.busy = false;
  state.done = true;
  const name = state.menu.generators.find((g) => g.id === r.generator)?.name || r.generator;
  $("foot-info").textContent = `Made with ${name} in ${Math.round(r.total_s)} s`
    + (r.gpu_peak_gb != null ? `, using ${r.gpu_peak_gb} GB of VRAM` : "");
  note($("note"), "Spin it around. Happy with the shape? Press Next. Not right? Press Redo for a new try.", "ok");
  render();
}

function fail(text) {
  state.busy = false;
  showMsg(state.done ? "" : "Your model will appear here. Press Make 3D model to try again.");
  note($("note"), text, "error");
  $("foot-info").textContent = "";
  render();
}

async function init() {
  $("file").onchange = (e) => chooseFile(e.target.files[0]);
  const drop = $("drop");
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    chooseFile(e.dataTransfer.files[0]);
  };
  $("from-text").onclick = () => note($("note"),
    "Describing a character in words is coming next. For now, choose a picture.");
  $("next").onclick = async () => {
    if (state.step === 2) {
      try {
        await api(`/api/assets/${state.asset.id}/clean`, { method: "POST" });
      } catch (e) {
        note($("note2"), e.message);
      }
      return;
    }
    if (state.done) { state.step = 2; render(); } else start();
  };
  $("redo").onclick = () => start();
  try {
    buildMenu(await api("/api/menu"));
  } catch {
    showMsg("I could not reach Asset Forge. Close this page and open AssetForge again.", "error");
  }
  render();
}
init();
