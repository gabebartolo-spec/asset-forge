import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// A big spinnable viewer. Shows the raw mesh as grey clay (the generators make shape only); the
// cleaned model is shown with its own colour (`textured`).
export class Viewer {
  constructor(el) {
    this.el = el;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
    this.camera.position.set(0, 0.6, 3);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3f4a, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2);
    sun.position.set(2, 3, 2.5);
    this.scene.add(sun);
    const rim = new THREE.DirectionalLight(0x88aaff, 0.9);
    rim.position.set(-3, 1, -2);
    this.scene.add(rim);
    this.grid = new THREE.GridHelper(4, 16, 0x3a404c, 0x2a2f38);
    this.scene.add(this.grid);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.model = null;
    this.ready = false;
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    this.markers = null;
    this.mixer = null;
    this.clock = new THREE.Clock();
    this.playing = null; // { action, speed } while a clip plays (Step 4)
    this.chains = null; // a monster's limb markers (editChains)
    this.initChainPointer();
    this.renderer.setAnimationLoop(() => {
      this.tickClip(this.clock.getDelta());
      this.controls.update();
      this.updateMarkers();
      this.renderer.render(this.scene, this.camera);
    });
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  clear() {
    if (this.model) this.scene.remove(this.model);
    if (this.markers) this.scene.remove(this.markers.group);
    this.chains = null; // its markers live inside the model and go with it
    this.addPick = null;
    this.model = null;
    this.markers = null;
    this.mixer = null;
    this.playing = null;
    this.grid.position.z = 0;
    this.ready = false;
  }

  // keepView: swap the model but leave the camera where the user put it.
  async load(url, { keepView = false, pose = false, showBones = false, textured = false } = {}) {
    const gltf = await new GLTFLoader().loadAsync(url);
    this.clear();
    const clay = new THREE.MeshStandardMaterial({ color: 0xc9ccd4, roughness: 0.7, metalness: 0.0 });
    const root = gltf.scene;
    root.traverse((o) => {
      if (o.isMesh) {
        if (!o.geometry.attributes.normal) o.geometry.computeVertexNormals();
        if (!textured) o.material = clay; // textured: the cleaned model's own colour
      }
    });
    // stand it on the grid, centred, about 1.6 units tall
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const scale = 1.6 / Math.max(size.x, size.y, size.z, 1e-6);
    root.scale.setScalar(scale);
    box.setFromObject(root);
    const c = box.getCenter(new THREE.Vector3());
    root.position.set(-c.x, -box.min.y, -c.z);
    this.root = root;
    const holder = new THREE.Group();
    holder.add(root);
    this.scene.add(holder);
    this.model = holder;
    this.root = root;
    this.unit = scale;              // viewer units per metre
    this.anims = gltf.animations;
    const h = box.max.y - box.min.y;
    if (!keepView) {
      this.controls.target.set(0, h / 2, 0);
      this.camera.position.set(1.6, h * 0.75, 3.0);
      this.controls.update();
    }
    this.buildMarkers(root, h);
    this.setBones(showBones);
    if (pose && gltf.animations.length) { // freeze the quick test pose (the clip's last frame)
      this.mixer = new THREE.AnimationMixer(root);
      const clip = gltf.animations[0];
      this.mixer.clipAction(clip).play();
      this.mixer.setTime(clip.duration);
      root.updateMatrixWorld(true);
    }
    this.ready = true;
  }

  // Joint dots and the lines between them, drawn on top of the body so they can be seen.
  buildMarkers(root, height) {
    const bones = [];
    root.traverse((o) => { if (o.isBone) bones.push(o); });
    if (!bones.length) return;
    const group = new THREE.Group();
    group.visible = false;
    group.renderOrder = 10;
    const dotGeo = new THREE.SphereGeometry(height * 0.012, 12, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffd23f, depthTest: false, transparent: true });
    const lineMat = new THREE.LineBasicMaterial({ color: 0x4fd0ff, depthTest: false, transparent: true });
    const dots = bones.map((b) => {
      const d = new THREE.Mesh(dotGeo, dotMat);
      d.renderOrder = 11;
      group.add(d);
      return d;
    });
    const pairs = [];
    bones.forEach((b, i) => {
      const j = bones.indexOf(b.parent);
      if (j >= 0) pairs.push([j, i]);
    });
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pairs.length * 6), 3));
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    lines.frustumCulled = false;
    lines.renderOrder = 10;
    group.add(lines);
    this.scene.add(group);
    this.markers = { group, bones, dots, pairs, lines };
  }

  updateMarkers() {
    const m = this.markers;
    if (!m || !m.group.visible) return;
    const v = new THREE.Vector3();
    const pos = m.lines.geometry.attributes.position;
    m.bones.forEach((b, i) => { b.getWorldPosition(v); m.dots[i].position.copy(v); });
    m.pairs.forEach(([a, b], k) => {
      pos.setXYZ(k * 2, ...m.dots[a].position.toArray());
      pos.setXYZ(k * 2 + 1, ...m.dots[b].position.toArray());
    });
    pos.needsUpdate = true;
  }

  // Step 4: play one clip on a loop at game speed. The clips are in place, so the grid runs
  // under the feet at the clip's ground speed (m/s): a planted foot should stay on its square.
  playClip(name, speed = 0) {
    const clip = (this.anims || []).find((c) => c.name === name);
    if (!clip || !this.root) return false;
    this.mixer = this.mixer || new THREE.AnimationMixer(this.root);
    this.mixer.stopAllAction();
    const action = this.mixer.clipAction(clip);
    action.reset().setLoop(THREE.LoopRepeat, Infinity).play();
    this.playing = { action, speed };
    this.grid.position.z = 0;
    return true;
  }

  tickClip(dt) {
    if (!this.playing || !this.mixer) return;
    this.mixer.update(dt);
    const cell = 4 / 16; // the grid's square
    const z = this.grid.position.z - this.playing.speed * this.unit * dt;
    this.grid.position.z = ((z % cell) + cell) % cell - cell; // forward is +Z, the ground runs back
  }

  setBones(on) {
    if (this.markers) this.markers.group.visible = on;
  }

  // ---- a monster's limb markers: drag a dot, click the body to add a limb (Step 3) ----
  // Points come and go in the Clean step's frame (metres, Z up, faces -Y); glTF is Y up, so a
  // point (x, y, z) sits at (x, z, -y) inside the loaded model, which carries its scale.

  editChains(chain, { onMove, selected = -1 } = {}) {
    if (!this.root) return;
    if (this.chains) this.root.remove(this.chains.group);
    const group = new THREE.Group();
    const r = (chain.height || 1) * 0.022;
    const geo = new THREE.SphereGeometry(r, 14, 10);
    const mat = (c) => new THREE.MeshBasicMaterial({ color: c, depthTest: false, transparent: true });
    const spineMat = mat(0x4fd0ff), limbMat = mat(0xffd23f), selMat = mat(0xff7a3d);
    const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.8 });
    const dots = [], lines = [];
    const add = (pts, m, owner) => {
      const ds = pts.map((p, j) => {
        const d = new THREE.Mesh(geo, m);
        d.position.set(p[0], p[2], -p[1]);
        d.renderOrder = 12;
        d.userData = { owner, joint: j };
        group.add(d);
        dots.push(d);
        return d;
      });
      const g = new THREE.BufferGeometry().setFromPoints(ds.map((d) => d.position));
      const line = new THREE.Line(g, lineMat);
      line.renderOrder = 11;
      line.frustumCulled = false;
      group.add(line);
      lines.push({ line, ds });
    };
    add(chain.spine, spineMat, -1);
    chain.limbs.forEach((lb, i) => add(lb.joints, i === selected ? selMat : limbMat, i));
    this.root.add(group);
    this.chains = { group, dots, lines, chain, onMove };
  }

  // the next click on the body gives a point there (Add a limb: where its tip is)
  pickOnBody(cb) { this.addPick = cb; this.renderer.domElement.style.cursor = cb ? "crosshair" : ""; }

  initChainPointer() {
    const el = this.renderer.domElement, ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
    const plane = new THREE.Plane(), hit = new THREE.Vector3();
    let drag = null;
    const aim = (e) => {
      const b = el.getBoundingClientRect();
      ndc.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(ndc, this.camera);
    };
    const toFrame = (v) => { const p = this.root.worldToLocal(v.clone()); return [p.x, -p.z, p.y]; };
    el.addEventListener("pointerdown", (e) => {
      if (!this.root || e.button !== 0) return;
      aim(e);
      if (this.addPick) {
        const meshes = [];
        this.root.traverse((o) => { if (o.isMesh && !(this.chains && o.parent === this.chains.group)) meshes.push(o); });
        const h = ray.intersectObjects(meshes, false)[0];
        if (!h) return;
        const cb = this.addPick;
        this.pickOnBody(null);
        e.stopImmediatePropagation();
        cb(toFrame(h.point));
        return;
      }
      if (!this.chains) return;
      const h = ray.intersectObjects(this.chains.dots, false)[0];
      if (!h) return;
      e.stopImmediatePropagation(); // the dot moves, not the camera
      this.controls.enabled = false;
      const d = h.object, w = d.getWorldPosition(new THREE.Vector3());
      plane.setFromNormalAndCoplanarPoint(this.camera.getWorldDirection(new THREE.Vector3()), w);
      drag = d;
      el.setPointerCapture(e.pointerId);
    }, { capture: true });
    el.addEventListener("pointermove", (e) => {
      if (!this.chains) return;
      aim(e);
      if (!drag) {
        el.style.cursor = this.addPick ? "crosshair"
          : ray.intersectObjects(this.chains.dots, false).length ? "grab" : "";
        return;
      }
      if (!ray.ray.intersectPlane(plane, hit)) return;
      drag.position.copy(this.root.worldToLocal(hit.clone()));
      this.chains.lines.forEach(({ line, ds }) => {
        if (ds.includes(drag)) line.geometry.setFromPoints(ds.map((x) => x.position));
      });
    });
    const end = () => {
      if (!drag) return;
      const { owner, joint } = drag.userData, p = drag.position;
      const pt = [p.x, -p.z, p.y].map((c) => Math.round(c * 1e4) / 1e4);
      const ch = this.chains.chain;
      (owner < 0 ? ch.spine : ch.limbs[owner].joints)[joint] = pt;
      drag = null;
      this.controls.enabled = true;
      if (this.chains.onMove) this.chains.onMove(owner, joint, pt);
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  }
}
