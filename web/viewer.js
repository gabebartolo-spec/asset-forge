import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// A big spinnable viewer. Shows the raw mesh as grey clay (the generators make shape only).
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
    this.chains = null; // a monster's limb markers (editChains)
    this.initChainPointer();
    this.renderer.setAnimationLoop(() => {
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
    this.model = null;
    this.markers = null;
    this.mixer = null;
    this.ready = false;
  }

  // keepView: swap the model but leave the camera where the user put it.
  // tips: [{name, bone, at: [x, y, z]}] the end of each limb (a bone has no dot at its tail);
  // red: names of joints to mark red (they sit outside the body).
  async load(url, { keepView = false, pose = false, showBones = false, tips = [], red = [] } = {}) {
    const gltf = await new GLTFLoader().loadAsync(url);
    this.clear();
    const clay = new THREE.MeshStandardMaterial({ color: 0xc9ccd4, roughness: 0.7, metalness: 0.0 });
    const root = gltf.scene;
    root.traverse((o) => {
      if (o.isMesh) {
        if (!o.geometry.attributes.normal) o.geometry.computeVertexNormals();
        o.material = clay;
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
    const h = box.max.y - box.min.y;
    if (!keepView) {
      this.controls.target.set(0, h / 2, 0);
      this.camera.position.set(1.6, h * 0.75, 3.0);
      this.controls.update();
    }
    holder.updateMatrixWorld(true);
    this.buildMarkers(root, h, tips, new Set(red));
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
  buildMarkers(root, height, tips = [], red = new Set()) {
    const bones = [];
    root.traverse((o) => { if (o.isBone) bones.push(o); });
    if (!bones.length) return;
    for (const t of tips) { // a point fixed to the limb's last bone, so it moves with the pose
      const b = bones.find((x) => x.name === t.bone);
      if (!b) continue;
      const anchor = new THREE.Object3D();
      anchor.name = t.name;
      anchor.position.copy(b.worldToLocal(root.localToWorld(new THREE.Vector3(t.at[0], t.at[2], -t.at[1]))));
      b.add(anchor);
      bones.push(anchor);
    }
    const group = new THREE.Group();
    group.visible = false;
    group.renderOrder = 10;
    const dotGeo = new THREE.SphereGeometry(height * 0.012, 12, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffd23f, depthTest: false, transparent: true });
    const redMat = new THREE.MeshBasicMaterial({ color: 0xff4040, depthTest: false, transparent: true });
    const redGeo = new THREE.SphereGeometry(height * 0.018, 12, 8);
    // white lines, as in the limb editor: one colour, one meaning
    const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true });
    const dots = bones.map((b) => {
      const d = red.has(b.name) ? new THREE.Mesh(redGeo, redMat) : new THREE.Mesh(dotGeo, dotMat);
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

  setBones(on) {
    if (this.markers) this.markers.group.visible = on;
  }

  // ---- a monster's limb markers: drag a dot to where its joint is (Step 3) ----
  // Points come and go in the Clean step's frame (metres, Z up, faces -Y); glTF is Y up, so a
  // point (x, y, z) sits at (x, z, -y) inside the loaded model, which carries its scale.

  // red: [[limb, joint]] markers outside the body (limb -1: the body line); onGrab(limb) when a
  // dot is picked up, onMove(limb, joint, point) when it is put down.
  editChains(chain, { onMove, onGrab, selected = -1, red = [] } = {}) {
    if (!this.root) return;
    if (this.chains) this.root.remove(this.chains.group);
    const group = new THREE.Group();
    const r = (chain.height || 1) * 0.022;
    const geo = new THREE.SphereGeometry(r, 14, 10);
    const mat = (c) => new THREE.MeshBasicMaterial({ color: c, depthTest: false, transparent: true });
    const spineMat = mat(0x4fd0ff), limbMat = mat(0xffd23f), selMat = mat(0xff7a3d), redMat = mat(0xff4040);
    const isRed = (owner, j) => red.some(([a, b]) => a === owner && b === j);
    const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.8 });
    const dots = [], lines = [];
    const add = (pts, m, owner) => {
      const ds = pts.map((p, j) => {
        const d = new THREE.Mesh(geo, isRed(owner, j) ? redMat : m);
        d.position.set(p[0], p[2], -p[1]);
        d.renderOrder = 12;
        d.userData = { owner, joint: j, red: isRed(owner, j) };
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
    this.chains = { group, dots, lines, chain, onMove, onGrab, mats: { spineMat, limbMat, selMat, redMat } };
  }

  // show limb i in orange (or none: -1) without rebuilding the markers (hover, drag)
  highlightChain(i) {
    if (!this.chains) return;
    const { spineMat, limbMat, selMat, redMat } = this.chains.mats;
    this.chains.dots.forEach((d) => {
      const { owner, red } = d.userData;
      d.material = red ? redMat : owner < 0 ? spineMat : owner === i ? selMat : limbMat;
    });
  }

  initChainPointer() {
    const el = this.renderer.domElement, ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
    const plane = new THREE.Plane(), hit = new THREE.Vector3();
    let drag = null;
    const aim = (e) => {
      const b = el.getBoundingClientRect();
      ndc.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(ndc, this.camera);
    };
    el.addEventListener("pointerdown", (e) => {
      if (!this.root || e.button !== 0) return;
      aim(e);
      if (!this.chains) return;
      const h = ray.intersectObjects(this.chains.dots, false)[0];
      if (!h) return;
      e.stopImmediatePropagation(); // the dot moves, not the camera
      this.controls.enabled = false;
      const d = h.object, w = d.getWorldPosition(new THREE.Vector3());
      plane.setFromNormalAndCoplanarPoint(this.camera.getWorldDirection(new THREE.Vector3()), w);
      drag = d;
      el.setPointerCapture(e.pointerId);
      if (this.chains.onGrab) this.chains.onGrab(d.userData.owner);
    }, { capture: true });
    el.addEventListener("pointermove", (e) => {
      if (!this.chains) return;
      aim(e);
      if (!drag) {
        el.style.cursor = ray.intersectObjects(this.chains.dots, false).length ? "grab" : "";
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
