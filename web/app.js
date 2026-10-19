import { Viewer } from "./viewer.js";

const $ = (id) => document.getElementById(id);
const state = {
  file: null, type: null, generator: null, asset: null,
  busy: false, done: false, step: 1, menu: null,
  cleanReady: false, rig: null, bones: false, pose: false, meshUrl: null,
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
  m.textContent = "";
  if (kind === "busy" && text) {
    const sp = document.createElement("div");
    sp.className = "spinner";
    m.append(sp);
  }
  text.split("\n").forEach((line, i) => {
    if (i) m.append(document.createElement("br"));
    m.append(document.createTextNode(line));
  });
  m.classList.toggle("hidden", !text);
}
function makerTime() {
  const g = state.menu && state.menu.generators.find((x) => x.id === state.generator);
  return g ? g.typical_time : "a few minutes";
}
function clock(s) {
  const t = Math.floor(s || 0);
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}
function makerVram(id) { // the same wording the maker card shows (one source: the menu)
  const g = state.menu && state.menu.generators.find((x) => x.id === id);
  return g ? g.vram.replace(/^uses /, "") : "";
}
function note(el, text, kind = "") {
  el.className = "note " + kind;
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

function render() {
  const onStep1 = state.step === 1;
  $("panel-1").classList.toggle("hidden", !onStep1);
  $("panel-2").classList.toggle("hidden", state.step !== 2);
  $("panel-3").classList.toggle("hidden", state.step !== 3);
  const pill3 = $("pill3");
  pill3.classList.toggle("clickable", state.cleanReady && state.step !== 3);
  pill3.onclick = state.cleanReady && state.step !== 3 ? () => goStep3() : null;
  $("pill3-soon").classList.toggle("hidden", state.cleanReady);
  document.querySelectorAll("#steps li").forEach((li) => {
    const n = Number(li.dataset.step);
    li.classList.toggle("current", n === state.step);
    li.classList.toggle("done", n < state.step);
  });
  const next = $("next"), redo = $("redo");
  const pill1 = $("pill1");
  pill1.classList.toggle("clickable", !onStep1);
  pill1.onclick = onStep1 ? null : () => backToStep1();
  redo.classList.toggle("hidden", !onStep1);
  const hint = $("foot-hint");
  hint.textContent = "";
  if (onStep1) {
    if (state.done && !state.busy) {
      next.textContent = "Next: Clean up";
      next.disabled = false;
    } else {
      next.textContent = state.busy ? "Working..." : "Make 3D model";
      next.disabled = !state.file || !state.type || state.busy;
      if (!state.busy && !state.done) {
        if (!state.file && !state.type) hint.textContent = "Pick a picture and say what it is, then press Make 3D model.";
        else if (!state.file) hint.textContent = "Pick a picture first.";
        else if (!state.type) hint.textContent = "Now say what it is (step 2).";
      }
    }
    redo.disabled = state.busy || !state.asset;
  } else if (state.step === 3) {
    next.textContent = state.busy ? "Working..." : state.rig ? "Next: Animate (coming next)" : "Build skeleton";
    next.disabled = state.busy || !!state.rig;
    $("skel-look").classList.toggle("hidden", !state.rig);
    $("skel-wait").classList.toggle("hidden", !!state.rig);
    $("tog-bones").setAttribute("aria-pressed", String(state.bones));
    $("tog-pose").setAttribute("aria-pressed", String(state.pose));
  } else {
    next.textContent = "Coming next";
    next.disabled = true;
  }
  $("panel-1").classList.toggle("busy", state.busy);
}

function buildMenu(menu) {
  state.menu = menu;
  const types = $("types");
  types.innerHTML = "";
  menu.types.forEach((t) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.value = t.id;
    b.textContent = t.label;
    b.onclick = () => selectType(t.id);
    types.append(b);
  });
  const gens = $("generators");
  gens.innerHTML = "";
  const sameTime = menu.generators.every((g) => g.typical_time === menu.generators[0].typical_time);
  $("same-time").textContent = sameTime ? `(each takes ${menu.generators[0].typical_time})` : "";
  menu.generators.forEach((g) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "gen";
    b.setAttribute("role", "radio");
    b.dataset.value = g.id;
    b.innerHTML = '<div><span class="name"></span><span class="label"></span></div><div class="blurb"></div><div class="facts"></div>';
    b.querySelector(".name").textContent = g.name;
    b.querySelector(".label").textContent = g.label;
    b.querySelector(".blurb").textContent = g.blurb;
    b.querySelector(".facts").textContent = sameTime
      ? g.vram.replace(/^uses/, "Uses") : `Takes ${g.typical_time}\n` + g.vram.replace(/^uses/, "Uses");
    b.onclick = () => selectGenerator(g.id);
    gens.append(b);
    if (g.selected) state.generator = g.id;
  });
  selectType(null);
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
  $("drop-text").textContent = "Change picture";
  note($("note"), "");
  render();
}

async function start() {
  if (state.busy || !state.file) return;
  state.busy = true;
  render();
  note($("note"), "");
  $("foot-info").textContent = "Making your model...";
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
    let text;
    if (j.state === "waiting") text = "Waiting for the graphics card (another job is running)...\nIt starts by itself when the graphics card is free. You can leave this open.";
    else if (j.state === "queued") text = j.ahead > 0 ? "Waiting for your turn...\nIt starts by itself when the graphics card is free. You can leave this open." : "Getting ready...";
    else text = `Making your model... ${clock(j.elapsed_s)}\nThis can take ${makerTime()}.`;
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
    + (makerVram(r.generator) ? `, using ${makerVram(r.generator)}` : "");
  note($("note"), "Happy with it? Press Next. Not right? Press Redo for a new try.", "ok");
  render();
}

const TYPE_WORDS = { humanoid: "a person", animal: "an animal", monster: "a monster" };

function fileUrl(step, name, v = "") {
  return `/api/assets/${state.asset.id}/files/${step}/${name}${v ? "?v=" + v : ""}`;
}

async function backToStep1() {
  state.step = 1;
  render();
  if (state.meshUrl && viewer) {
    try { await viewer.load(state.meshUrl); } catch { /* keep whatever is shown */ }
  }
}

// Step 3. TODO(PR #9): Step 2 will call this itself once its clean.glb is written.
async function goStep3() {
  state.step = 3;
  $("skel-type").textContent = `This is ${TYPE_WORDS[state.asset.type] || "a model"}, so it gets a ${
    state.asset.type === "humanoid" ? "human" : "animal"} skeleton.`;
  render();
  viewer = viewer || new Viewer($("viewer"));
  note($("note"), "");
  try {
    if (state.rig) await showRig(false);
    else {
      await viewer.load(fileUrl("clean", "clean.glb"));
      showMsg("");
    }
  } catch {
    note($("note"), "I could not show the model. Go back and try again.", "error");
  }
  $("viewer-hint").classList.remove("hidden");
  render();
}

async function showRig(keepView) {
  const name = state.pose ? "test_pose.glb" : "rigged.glb";
  await viewer.load(fileUrl("skeleton", name, state.rig.total_s), {
    keepView, pose: state.pose, showBones: state.bones });
  showMsg("");
}

async function buildSkeleton() {
  if (state.busy) return;
  state.busy = true;
  note($("note"), "");
  showMsg("Fitting the skeleton to your model...\nThis takes under a minute.", "busy");
  render();
  try {
    const job = await api(`/api/assets/${state.asset.id}/skeleton`, { method: "POST" });
    for (;;) {
      const j = await api(`/api/jobs/${job.id}`);
      if (j.state === "done") { state.rig = j.result; break; }
      if (j.state === "failed") throw new Error(j.error || j.message);
      showMsg(j.state === "running" ? `Fitting the skeleton... ${clock(j.elapsed_s)}`
        : "Waiting for your turn...\nIt starts by itself when the graphics card is free.", "busy");
      await new Promise((r) => setTimeout(r, 1000));
    }
    state.bones = true; // show the dots straight away: that is what to check first
    state.pose = false;
    await showRig(false);
    const r = state.rig;
    $("skel-facts").textContent = `Fitted ${r.bones} bones. Each part of the skin follows at most 4 of them, ${
      "so it stays light in a game."}`;
    $("foot-info").textContent = `Skeleton built in ${Math.round(r.total_s)} s`;
    note($("note"), "Check the dots sit inside the body, then try the quick pose.", "ok");
  } catch (e) {
    showMsg("");
    note($("note"), e.message, "error");
  }
  state.busy = false;
  render();
}

async function toggle(which) {
  if (!state.rig || state.busy) return;
  state[which] = !state[which];
  if (which === "bones") viewer.setBones(state.bones);
  else {
    try { await showRig(true); } catch { note($("note"), "I could not show the pose.", "error"); }
  }
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
  $("next").onclick = async () => {
    if (state.step === 3) return buildSkeleton();
    if (state.step === 2) return;
    if (state.done) { state.step = 2; render(); } else start();
  };
  $("redo").onclick = () => start();
  $("tog-bones").onclick = () => toggle("bones");
  $("tog-pose").onclick = () => toggle("pose");
  try {
    buildMenu(await api("/api/menu"));
  } catch {
    showMsg("I could not reach Asset Forge. Close this page and open AssetForge again.", "error");
  }
  render();
  // Dev hand-over until PR #9: /?asset=ID opens an existing library model that has a clean.glb.
  const id = new URLSearchParams(location.search).get("asset");
  if (id) {
    try {
      const a = await api(`/api/assets/${encodeURIComponent(id)}`);
      state.asset = a;
      state.cleanReady = !!(a.steps.clean && a.steps.clean.files.includes("clean.glb"));
      const g = a.steps.generate && a.steps.generate.result;
      if (g) state.meshUrl = `/api/assets/${a.id}/files/generate/${g.mesh}`;
      if (a.steps.skeleton && a.steps.skeleton.result) {
        state.rig = a.steps.skeleton.result;
        $("skel-facts").textContent = `Fitted ${state.rig.bones} bones.`;
        state.bones = true;
      }
      if (state.cleanReady) await goStep3();
    } catch (e) { note($("note"), e.message, "error"); }
  }
}
init();
