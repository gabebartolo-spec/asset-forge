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
    this.model = null;
    this.markers = null;
    this.mixer = null;
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

  setBones(on) {
    if (this.markers) this.markers.group.visible = on;
  }
}
