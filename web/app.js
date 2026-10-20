import { Viewer } from "./viewer.js";
import * as lib from "./library.js";

const $ = (id) => document.getElementById(id);
const state = {
  file: null, type: null, generator: null, asset: null,
  busy: false, done: false, step: 1, menu: null,
  cleanReady: false, rig: null, bones: false, pose: false, meshUrl: null,
  expanding: false, source: "", variation: 0, // "Expand my idea": the words it started from
  reference: false, refUrl: "",               // text-only: the drawn picture is ready to check
  showing: null,                              // what the viewer shows: "model", "ref" or null
  limbWarn: "",                               // Step 1: the model's legs or arms do not match the words
  chain: null, limbSel: -1, adding: false,    // Step 3, monsters: the limb chains being checked
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
const post = (path, data) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

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
function showRef(text) { // the drawn reference picture, shown before the 3D run
  const m = $("viewer-msg");
  m.className = "viewer-msg ref";
  m.textContent = "";
  const img = document.createElement("img");
  img.alt = "The picture drawn from your words";
  img.src = state.refUrl;
  m.append(img, document.createTextNode(text));
  state.showing = "ref";
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
  redo.classList.toggle("hidden", !onStep1 || !state.asset);
  const hint = $("foot-hint");
  hint.textContent = "";
  const words = $("idea").value.trim();
  const textOnly = !state.file && !!words;
  const canDraw = !!(state.menu && state.menu.text_draw.available);
  if (onStep1) {
    if (state.done && !state.busy) {
      next.textContent = "Next: Clean up";
      next.disabled = false;
    } else {
      const needDraw = textOnly && !state.reference;
      next.textContent = state.busy ? "Working..." : (needDraw && canDraw ? "Draw a picture" : "Make 3D model");
      const haveInput = state.file || (textOnly && (state.reference || canDraw));
      next.disabled = !haveInput || !state.type || state.busy || state.expanding;
      if (!state.busy && !state.done) {
        if (!state.file && !words && !state.type) hint.textContent = "Pick a picture or describe your model, and say what it is, then press Make 3D model.";
        else if (!state.file && !words) hint.textContent = "Pick a picture or describe your model first.";
        else if (!state.type) hint.textContent = "Now say what it is (step 2).";
        else if (needDraw && canDraw) hint.textContent = "Press Draw a picture. You can check it before the 3D model is made.";
      }
    }
    redo.disabled = state.busy || state.expanding || !state.asset;
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
  const ih = $("idea-hint");
  const wordCount = words ? words.split(/\s+/).length : 0;
  const noDraw = !!(state.menu && !state.menu.text_draw.available);
  $("draw-note").textContent = noDraw ? state.menu.text_draw.note : "";
  $("draw-note").classList.toggle("hidden", !(noDraw && !state.file && (state.source || wordCount >= 3)));
  $("expand-why").classList.toggle("hidden", !(words && !state.type));
  $("expand").disabled = !words || !state.type || state.busy || state.expanding;
  $("expand").textContent = state.expanding ? "Writing..." : "Expand my idea";
  $("reroll").classList.toggle("hidden", !state.source);
  $("reroll").disabled = state.busy || state.expanding || !state.type;
  $("idea").disabled = state.busy || state.expanding;
  if (!state.expanding && !ih.classList.contains("error")) {
    ih.textContent = !words ? "Type a few words, then press Expand my idea. You can edit the result."
      : !state.type ? ""
      : state.file ? "Your picture builds the model; your words are kept as notes."
      : state.source ? "Edit it if you like. Not quite right? Try another version." : "";
  }
  limbWarningButtons(onStep1);
  limbEditorShown();
  grow();
  $("viewer-hint").classList.toggle("hidden", !(state.showing === "model" && !state.busy));
  $("panel-1").classList.toggle("busy", state.busy);
}

function grow() { // the box grows with its text (about 8 lines), then scrolls
  const t = $("idea");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight + 2, 200) + "px";
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
function newInput() { // the picture or words changed: the old model and drawn picture no longer match
  state.asset = null;
  state.done = false;
  state.reference = false;
}
function selectType(id) {
  if (state.asset && id !== state.type) newInput(); // new type = new model
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
  newInput();
  $("preview").src = URL.createObjectURL(file);
  $("preview").classList.remove("hidden");
  $("drop").classList.add("has-image");
  $("drop-text").textContent = "Change picture";
  note($("note"), "");
  render();
}

// Follow a job until it ends. `what` is the plain-words name of the work; the footer says
// "Waiting for the graphics card..." while the job is only queued and the work once it runs.
async function follow(jobId, what, onTick) {
  for (;;) {
    const j = await api(`/api/jobs/${jobId}`);
    if (j.state === "done") return j;
    if (j.state === "failed") throw new Error(j.error || j.message);
    let text, foot;
    if (j.state === "waiting") {
      foot = "Waiting for the graphics card...";
      text = "Waiting for the graphics card (another job is running)...\nIt starts by itself when the graphics card is free. You can leave this open.";
    } else if (j.state === "queued") {
      foot = "Waiting for the graphics card...";
      text = j.ahead > 0 ? "Waiting for your turn...\nIt starts by itself when the graphics card is free. You can leave this open." : "Getting ready...";
    } else {
      foot = what.foot;
      text = `${what.foot} ${clock(j.elapsed_s)}\n${what.takes()}`;
    }
    onTick(foot, text, j.state);
    await new Promise((r) => setTimeout(r, 1000));
  }
}
const MODEL = { foot: "Making your model...", takes: () => `This can take ${makerTime()}.` };
const PICTURE = { foot: "Drawing your picture...", takes: () => "This takes about a minute." };
const WRITING = { foot: "Writing your description...", takes: () => "" };
const busyTick = (foot, text) => { $("foot-info").textContent = foot; showMsg(text, "busy"); };

async function start() {
  if (state.busy) return;
  if (!state.file && !state.reference) return drawPicture();
  state.busy = true;
  state.limbWarn = "";
  render();
  note($("note"), "");
  $("foot-info").textContent = "Getting ready...";
  showMsg(state.file ? "Sending your picture..." : "Getting ready...", "busy");
  try {
    if (!state.asset) {
      const fd = new FormData();
      fd.append("image", state.file);
      fd.append("type", state.type);
      state.asset = await api("/api/assets", { method: "POST", body: fd });
    }
    // a new seed every time: Redo keeps the picture and changes the roll of the dice
    const job = await post(`/api/assets/${state.asset.id}/generate`, { generator: state.generator });
    await finish(await follow(job.id, MODEL, busyTick));
  } catch (e) {
    fail(e.message);
  }
}

async function drawPicture() { // text only: draw the reference first, so it can be checked
  state.busy = true;
  state.done = false;
  render();
  note($("note"), "");
  $("foot-info").textContent = "Getting ready...";
  showMsg("Getting ready...", "busy");
  const words = $("idea").value.trim();
  try {
    if (!state.asset) state.asset = await post("/api/assets/from-text", { prompt: words, type: state.type });
    const job = await post(`/api/assets/${state.asset.id}/draw`, { prompt: words });
    await follow(job.id, PICTURE, busyTick);
    state.refUrl = `/api/assets/${state.asset.id}/files/generate/input.png?v=${job.id}`;
    state.reference = true;
    state.busy = false;
    $("foot-info").textContent = "Your picture is ready";
    showRef("Happy with it? Press Make 3D model. Not right? Press Redo for another picture.");
    render();
  } catch (e) {
    fail(e.message);
  }
}

async function finish(job) {
  const r = job.result;
  showMsg("Loading the model...", "busy");
  try {
    viewer = viewer || new Viewer($("viewer"));
    state.meshUrl = `/api/assets/${job.asset_id}/files/generate/${r.mesh}?v=${job.id}`;
    await viewer.load(state.meshUrl);
  } catch {
    return fail("The model was made but I could not show it. Press Redo to try again.");
  }
  showMsg("");
  state.showing = "model";
  state.busy = false;
  state.done = true;
  const name = state.menu.generators.find((g) => g.id === r.generator)?.name || r.generator;
  $("foot-info").textContent = `Made with ${name} in ${Math.round(r.total_s)} s`
    + (makerVram(r.generator) ? `, using ${makerVram(r.generator)}` : "");
  showLimbCheck(r.anatomy);
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
  state.showing = "model";
  $("skel-type").textContent = state.asset.type === "monster"
    ? "This is a monster, so its skeleton comes from its shape."
    : `This is ${TYPE_WORDS[state.asset.type] || "a model"}, so it gets a ${
      state.asset.type === "humanoid" ? "human" : "animal"} skeleton.`;
  render();
  viewer = viewer || new Viewer($("viewer"));
  note($("note"), "");
  try {
    if (state.rig) await showRig(false);
    else {
      await viewer.load(fileUrl("clean", "clean.glb"));
      showMsg("");
      if (state.asset.type === "monster") await loadLimbs();
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
    const job = state.asset.type === "monster"
      ? await post(`/api/assets/${state.asset.id}/skeleton`, confirmedLimbs())
      : await api(`/api/assets/${state.asset.id}/skeleton`, { method: "POST" });
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
    state.chain = null; // the built skeleton is shown now; Change the limbs brings them back
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
  if (state.reference) showRef("Your picture is still here. Press Make 3D model to try again.");
  else if (state.done) showMsg("");
  else {
    showMsg("Your model will appear here. Press Make 3D model to try again.");
    state.showing = null;
  }
  note($("note"), text, "error");
  $("foot-info").textContent = "";
  render();
}

async function expand(again) {
  if (state.expanding || state.busy) return;
  const ih = $("idea-hint");
  if (!again) { state.source = $("idea").value.trim(); state.variation = 0; }
  else state.variation += 1;
  state.expanding = true;
  ih.classList.remove("error");
  render();
  ih.textContent = "Writing your description... The first time takes a few seconds longer.";
  try {
    const job = await post("/api/expand", { idea: state.source, type: state.type, variation: state.variation });
    const j = await follow(job.id, WRITING, (_foot, _text, st) => {
      ih.textContent = st === "running"
        ? "Writing your description... The first time takes a few seconds longer."
        : "Waiting for the graphics card...";
    });
    $("idea").value = j.result.prompt;
    grow();
    if (!state.file) newInput();
    if (state.showing === "ref") { showMsg("Your model will appear here."); state.showing = null; }
    ih.textContent = "";
  } catch (e) {
    if (!again) state.source = "";
    ih.textContent = e.message;
    ih.classList.add("error");
  }
  state.expanding = false;
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
  $("idea").oninput = () => {
    $("idea-hint").classList.remove("error");
    if (!state.file) newInput();
    render();
  };
  $("expand").onclick = () => expand(false);
  $("reroll").onclick = () => expand(true);
  $("next").onclick = async () => {
    if (state.step === 3) return buildSkeleton();
    if (state.step === 2) return;
    if (state.done) { state.step = 2; render(); } else start();
  };
  $("redo").onclick = () => (state.file || state.done ? start() : drawPicture());
  $("tog-bones").onclick = () => toggle("bones");
  $("tog-pose").onclick = () => toggle("pose");
  $("limb-add").onclick = () => addLimb();
  $("limb-again").onclick = () => changeLimbs();
  try {
    buildMenu(await api("/api/menu"));
  } catch {
    showMsg("I could not reach Asset Forge. Close this page and open AssetForge again.", "error");
  }
  render();
  lib.initLibrary({
    api, post, open: openAsset, generator: () => state.generator,
    types: () => (state.menu ? state.menu.types : []),
    drawNote: () => (state.menu && !state.menu.text_draw.available ? state.menu.text_draw.note : ""),
  });
  $("tab-3d").onclick = () => showTab("3d");
  $("tab-lib").onclick = () => showTab("lib");
  // /?asset=ID opens an existing library model (also what the Library's Open button does).
  const id = new URLSearchParams(location.search).get("asset");
  if (id) await openAsset(id);
}

function showTab(which) { // "3d" or "lib"
  document.body.classList.toggle("lib", which === "lib");
  $("tab-3d").classList.toggle("active", which === "3d");
  $("tab-lib").classList.toggle("active", which === "lib");
  if (which === "lib") lib.show(); else lib.hide();
}

// Open a Library model where it left off (or at `step`: "generate" shows the made model).
async function openAsset(id, step) {
  if (state.busy || state.expanding) { showTab("3d"); return; }
  let a;
  try { a = await api(`/api/assets/${encodeURIComponent(id)}`); } catch (e) {
    showTab("3d"); note($("note"), e.message, "error"); return;
  }
  showTab("3d");
  const g = a.steps.generate || {};
  const hasPic = (g.files || []).includes("input.png");
  state.file = null; state.rig = null; state.bones = state.pose = false;
  state.done = state.reference = false; state.meshUrl = null; state.step = 1; state.source = "";
  state.asset = null;
  state.limbWarn = ""; state.chain = null; state.limbSel = -1; state.adding = false;
  selectType(a.type);
  state.asset = a;
  if (g.settings && state.menu.generators.some((x) => x.id === g.settings.generator)) selectGenerator(g.settings.generator);
  $("idea").value = a.prompt || "";
  $("preview").classList.toggle("hidden", !hasPic);
  if (hasPic) $("preview").src = fileUrl("generate", "input.png", Date.now());
  $("drop").classList.toggle("has-image", hasPic);
  $("drop-text").textContent = hasPic ? "Change picture" : "Click to choose a picture";
  state.cleanReady = !!(a.steps.clean && a.steps.clean.files.includes("clean.glb"));
  note($("note"), "");
  $("foot-info").textContent = "";
  viewer = viewer || new Viewer($("viewer"));
  if (g.result) {
    state.meshUrl = fileUrl("generate", g.result.mesh);
    state.done = true;
    if (a.steps.skeleton && a.steps.skeleton.result) {
      state.rig = a.steps.skeleton.result;
      $("skel-facts").textContent = `Fitted ${state.rig.bones} bones.`;
      state.bones = true;
    }
  } else if (hasPic) {
    state.refUrl = fileUrl("generate", "input.png", Date.now());
    state.reference = true;
  }
  grow();
  if (state.cleanReady && step !== "generate") { await goStep3(); return; }
  if (state.done) {
    try { await viewer.load(state.meshUrl); showMsg(""); state.showing = "model"; } catch {
      note($("note"), "I could not show the model. Press Redo to make it again.", "error");
    }
    const name = state.menu.generators.find((x) => x.id === g.result.generator)?.name || g.result.generator;
    $("foot-info").textContent = `Made with ${name} in ${Math.round(g.result.total_s)} s`;
    showLimbCheck(g.result.anatomy);
  } else if (state.reference) {
    showRef("Happy with it? Press Make 3D model. Not right? Press Redo for another picture.");
  } else {
    showMsg("Your model will appear here.\nPress Draw a picture to start.");
    state.showing = null;
  }
  render();
}

// ---- Step 1: the limb check (legs and arms against the words) ----

function showLimbCheck(anatomy) {
  state.limbWarn = anatomy && anatomy.ok === false ? anatomy.message : "";
  if (state.limbWarn) note($("note"), state.limbWarn, "warn");
  else note($("note"), "Happy with it? Press Next. Not right? Press Redo for a new try.", "ok");
}

// A wrong count makes Re-roll the main button and Next a quieter "Use it anyway".
function limbWarningButtons(onStep1) {
  const warn = onStep1 && state.done && !state.busy && !!state.limbWarn;
  const next = $("next"), redo = $("redo");
  next.className = warn ? "secondary" : "primary";
  redo.className = warn ? "primary" : "secondary";
  redo.textContent = warn ? "Re-roll" : "Redo";
  if (warn) next.textContent = "Use it anyway";
}

// ---- Step 3, monsters: check the limb chains the app found, then Build skeleton ----

const KIND_NAMES = { leg: "Leg", arm: "Arm", head: "Head", tail: "Tail" };

async function loadLimbs() {
  try {
    state.chain = await api(`/api/assets/${state.asset.id}/skeleton/limbs`);
  } catch (e) {
    note($("note"), e.message, "error");
    return;
  }
  state.limbSel = -1;
  showLimbs();
  const c = state.chain.counts || {};
  const said = ["legs", "arms", "heads", "tails"].filter((k) => c[k]).map((k) => `${c[k]} ${
    c[k] === 1 ? k.slice(0, -1) : k}`);
  $("limb-hint").textContent = state.chain.confirmed ? "These are the limbs you confirmed last time."
    : said.length ? `I found ${said.join(", ")}.` : "I could not find any limbs. Add them yourself.";
  note($("note"), "Check the limbs, then press Build skeleton.", "ok");
}

function limbSide(lb) { // the character's left is +X, as in the skeleton's bone names
  const mid = state.chain.spine.reduce((t, p) => t + p[0], 0) / state.chain.spine.length;
  const dx = lb.joints[0][0] - mid;
  return Math.abs(dx) < 0.03 * (state.chain.height || 1) ? "middle" : dx > 0 ? "left" : "right";
}

function showLimbs() {
  viewer.editChains(state.chain, { selected: state.limbSel });
  const list = $("limb-list");
  list.textContent = "";
  const n = {};
  state.chain.limbs.forEach((lb, i) => {
    n[lb.kind] = (n[lb.kind] || 0) + 1;
    const li = document.createElement("li");
    li.classList.toggle("sel", i === state.limbSel);
    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "pick";
    pick.textContent = `${KIND_NAMES[lb.kind]} ${n[lb.kind]}, ${limbSide(lb)}`;
    pick.title = "Show this limb in orange";
    pick.onclick = () => { state.limbSel = i === state.limbSel ? -1 : i; showLimbs(); };
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "small secondary";
    rm.textContent = "Remove";
    rm.setAttribute("aria-label", `Remove ${pick.textContent}`);
    rm.onclick = () => removeLimb(i);
    li.append(pick, rm);
    list.append(li);
    if (i === state.limbSel) requestAnimationFrame(() => li.scrollIntoView({ block: "nearest" }));
  });
  render();
}

function removeLimb(i) {
  state.chain.limbs.splice(i, 1);
  state.limbSel = -1;
  $("limb-hint").textContent = "Removed. The body part stays in the model; it just will not move by itself.";
  showLimbs();
}

function addLimb() {
  if (state.adding) { // a second press cancels
    state.adding = false;
    viewer.pickOnBody(null);
    $("limb-hint").textContent = "";
    render();
    return;
  }
  state.adding = true;
  $("limb-hint").textContent = "Click on the model where the new limb's tip is.";
  viewer.pickOnBody((tip) => {
    state.adding = false;
    const base = nearestOnSpine(tip);
    const joints = [0, 1 / 3, 2 / 3, 1].map((t) => base.map((b, k) => Math.round((b + (tip[k] - b) * t) * 1e4) / 1e4));
    state.chain.limbs.push({ kind: $("limb-kind").value, joints });
    state.limbSel = state.chain.limbs.length - 1;
    $("limb-hint").textContent = "Added, in orange. Drag its dots to where its joints are.";
    showLimbs();
  });
  render();
}

function nearestOnSpine(p) { // the new limb joins the body at the closest point of the body line
  let best = null, bestD = Infinity;
  const sp = state.chain.spine;
  for (let k = 0; k + 1 < sp.length; k++) {
    const a = sp[k], ab = sp[k + 1].map((x, j) => x - a[j]);
    const len = ab.reduce((t, x) => t + x * x, 0) || 1e-9;
    const t = Math.max(0, Math.min(1, ab.reduce((t2, x, j) => t2 + x * (p[j] - a[j]), 0) / len));
    const q = a.map((x, j) => x + ab[j] * t);
    const d = q.reduce((t2, x, j) => t2 + (x - p[j]) ** 2, 0);
    if (d < bestD) { bestD = d; best = q; }
  }
  return best;
}

function confirmedLimbs() {
  return { spine: state.chain.spine, limbs: state.chain.limbs.map((lb) => ({ kind: lb.kind, joints: lb.joints })) };
}

function limbEditorShown() {
  const monster = !!(state.asset && state.asset.type === "monster");
  const editing = state.step === 3 && monster && !state.rig && !!state.chain;
  $("limb-edit").classList.toggle("hidden", !editing);
  $("limb-add").textContent = state.adding ? "Cancel" : "Add a limb";
  $("limb-add").disabled = state.busy;
  $("limb-again").classList.toggle("hidden", !(monster && state.rig));
  $("limb-again").disabled = state.busy;
  $("skel-wait").innerHTML = editing
    ? "When the limbs look right, press <b>Build skeleton</b>, bottom right."
    : "Press <b>Build skeleton</b>, bottom right. It takes under a minute.";
}

async function changeLimbs() { // back to the markers, starting from the limbs confirmed last time
  if (state.busy) return;
  state.rig = null;
  state.bones = state.pose = false;
  try {
    await viewer.load(fileUrl("clean", "clean.glb"));
    await loadLimbs();
  } catch {
    note($("note"), "I could not show the model. Go back and try again.", "error");
  }
  render();
}

init();
