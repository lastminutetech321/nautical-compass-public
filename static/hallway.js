import * as THREE from "three";

/**
 * Nautical Compass 3D Hallway
 * - Mobile safe
 * - Click/tap doors
 * - Drag to look
 * - Scroll/wheel to move
 * - Simple tween (no extra libs)
 */

const mount = document.getElementById("webglMount");
const fallback = document.getElementById("fallback");
const tooltip = document.getElementById("doorTooltip");
const doorTitle = document.getElementById("doorTitle");
const doorDesc = document.getElementById("doorDesc");
const doorEnterBtn = document.getElementById("doorEnterBtn");
const doorCloseBtn = document.getElementById("doorCloseBtn");

const DOORS = [
  {
    id: "NC_SERVICES",
    label: "Services",
    desc: "Clear, plain-English explanations of what we do — curated list + full catalog.",
    href: "/services",
    color: 0xb88a2a
  },
  {
    id: "SUBSCRIBE",
    label: "Subscribe",
    desc: "Unlock subscriber intake + dashboard access (Stripe checkout).",
    href: "/checkout",
    color: 0xe0b354
  },
  {
    id: "CONTRIBUTOR",
    label: "Contributor",
    desc: "Operators, staff, sales, builders, supply, sponsors — routed by fit & scoring.",
    href: "/contributor",
    color: 0x6dd5ff
  },
  {
    id: "PARTNER",
    label: "Partner",
    desc: "Manufacturers & vendors — partner intake and routing for supply relationships.",
    href: "/partner",
    color: 0x7ee787
  },
  {
    id: "PUBLIC_LEAD",
    label: "Lead",
    desc: "Public inquiry intake — non-subscriber entry point.",
    href: "/lead",
    color: 0xffc57a
  }
];

// ----- Utility: WebGL support check -----
function webglOk() {
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
  } catch {
    return false;
  }
}
if (!webglOk()) {
  fallback.style.display = "block";
  mount.style.display = "none";
  throw new Error("WebGL not available");
}

// ----- Renderer -----
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(mount.clientWidth, mount.clientHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
mount.appendChild(renderer.domElement);

// ----- Scene / Camera -----
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x060a14, 4, 55);

const camera = new THREE.PerspectiveCamera(65, mount.clientWidth / mount.clientHeight, 0.1, 200);
camera.position.set(0, 1.6, 5);

// ----- Lights -----
const ambient = new THREE.AmbientLight(0xffffff, 0.45);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0xffffff, 0.85);
keyLight.position.set(5, 8, 2);
scene.add(keyLight);

const rim = new THREE.PointLight(0xb88a2a, 0.8, 20);
rim.position.set(0, 2.4, -8);
scene.add(rim);

// ----- Hallway geometry -----
const hallLength = 48;
const hallWidth = 6;
const hallHeight = 3;

const floorMat = new THREE.MeshStandardMaterial({
  color: 0x0c162b,
  metalness: 0.15,
  roughness: 0.85
});
const wallMat = new THREE.MeshStandardMaterial({
  color: 0x0a1224,
  metalness: 0.05,
  roughness: 0.9
});
const ceilingMat = new THREE.MeshStandardMaterial({
  color: 0x08101f,
  metalness: 0.0,
  roughness: 0.95
});

const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(hallWidth, hallLength, 1, 1),
  floorMat
);
floor.rotation.x = -Math.PI / 2;
floor.position.z = -hallLength / 2 + 5;
scene.add(floor);

const leftWall = new THREE.Mesh(
  new THREE.PlaneGeometry(hallLength, hallHeight),
  wallMat
);
leftWall.rotation.y = Math.PI / 2;
leftWall.position.set(-hallWidth / 2, hallHeight / 2, -hallLength / 2 + 5);
scene.add(leftWall);

const rightWall = leftWall.clone();
rightWall.position.x = hallWidth / 2;
rightWall.rotation.y = -Math.PI / 2;
scene.add(rightWall);

const ceiling = new THREE.Mesh(
  new THREE.PlaneGeometry(hallWidth, hallLength),
  ceilingMat
);
ceiling.rotation.x = Math.PI / 2;
ceiling.position.set(0, hallHeight, -hallLength / 2 + 5);
scene.add(ceiling);

// Runner lights down the center
const runnerGeo = new THREE.PlaneGeometry(0.25, hallLength);
const runnerMat = new THREE.MeshBasicMaterial({ color: 0xb88a2a, transparent: true, opacity: 0.15 });
const runner = new THREE.Mesh(runnerGeo, runnerMat);
runner.rotation.x = -Math.PI / 2;
runner.position.set(0, 0.01, -hallLength / 2 + 5);
scene.add(runner);

// ----- Doors -----
const doors = [];
const doorGeo = new THREE.BoxGeometry(1.3, 2.2, 0.08);
const frameGeo = new THREE.BoxGeometry(1.45, 2.35, 0.12);

function makeDoor(door, idx, side) {
  const z = -6 - idx * 7;             // spaced down corridor
  const x = side === "L" ? -(hallWidth / 2) + 0.65 : (hallWidth / 2) - 0.65;

  const frameMat = new THREE.MeshStandardMaterial({
    color: 0x111b33,
    metalness: 0.15,
    roughness: 0.7
  });

  const doorMat = new THREE.MeshStandardMaterial({
    color: 0x0f1b33,
    metalness: 0.2,
    roughness: 0.7,
    emissive: new THREE.Color(door.color),
    emissiveIntensity: 0.08
  });

  const frame = new THREE.Mesh(frameGeo, frameMat);
  frame.position.set(x, 1.15, z);

  const slab = new THREE.Mesh(doorGeo, doorMat);
  slab.position.set(x, 1.1, z + (side === "L" ? 0.02 : 0.02));

  // Hinge pivot group so we can "open" a bit
  const pivot = new THREE.Group();
  pivot.position.set(x + (side === "L" ? -0.65 : 0.65), 0, z);
  slab.position.x = (side === "L" ? 0.65 : -0.65);
  slab.position.y = 1.1;
  slab.position.z = 0.02;
  pivot.add(slab);

  // Small label plate above door
  const plate = makeLabelSprite(door.label);
  plate.position.set(x, 2.55, z);
  scene.add(plate);

  // Store metadata
  frame.userData = { ...door, type: "door", side, pivot, slab };
  slab.userData = { ...door, type: "door", side, pivot, slab };

  scene.add(frame);
  scene.add(pivot);

  doors.push({ frame, pivot, slab, label: plate, meta: door, side, z });
}

function makeLabelSprite(text) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = "rgba(0,0,0,0)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // background
  ctx.fillStyle = "rgba(10,16,30,0.75)";
  roundRect(ctx, 8, 18, 496, 92, 18);
  ctx.fill();

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 2;
  roundRect(ctx, 8, 18, 496, 92, 18);
  ctx.stroke();

  ctx.font = "800 44px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial";
  ctx.fillStyle = "rgba(231,238,252,0.95)";
  ctx.fillText(text, 30, 78);

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(2.2, 0.55, 1);
  return sprite;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x+r, y);
  ctx.arcTo(x+w, y, x+w, y+h, r);
  ctx.arcTo(x+w, y+h, x, y+h, r);
  ctx.arcTo(x, y+h, x, y, r);
  ctx.arcTo(x, y, x+w, y, r);
  ctx.closePath();
}

makeDoor(DOORS[0], 0, "L");
makeDoor(DOORS[1], 0, "R");
makeDoor(DOORS[2], 1, "L");
makeDoor(DOORS[3], 1, "R");
makeDoor(DOORS[4], 2, "L");

// Accent light at the far end
const endLight = new THREE.PointLight(0xe0b354, 1.1, 24);
endLight.position.set(0, 2.1, -28);
scene.add(endLight);

// ----- Interaction (raycast) -----
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hoveredDoor = null;
let activeDoor = null;

function setPointerFromEvent(ev) {
  const rect = renderer.domElement.getBoundingClientRect();
  const cx = (ev.clientX - rect.left) / rect.width;
  const cy = (ev.clientY - rect.top) / rect.height;
  pointer.x = cx * 2 - 1;
  pointer.y = -(cy * 2 - 1);
}

function pickDoor() {
  raycaster.setFromCamera(pointer, camera);
  const objects = [];
  doors.forEach(d => { objects.push(d.frame, d.slab); });
  const hits = raycaster.intersectObjects(objects, false);
  if (!hits.length) return null;
  return hits[0].object.userData?.type === "door" ? hits[0].object.userData : null;
}

function highlightDoor(meta, on) {
  if (!meta || !meta.slab) return;
  const mat = meta.slab.material;
  mat.emissiveIntensity = on ? 0.35 : 0.08;
  mat.needsUpdate = true;
  // crack open a little on hover
  const target = on ? (meta.side === "L" ? 0.28 : -0.28) : 0;
  meta.pivot.rotation.y = lerp(meta.pivot.rotation.y, target, 0.35);
}

// ----- Camera controls -----
let yaw = 0;
let pitch = 0;
let dragging = false;
let lastX = 0;
let lastY = 0;

function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }
function lerp(a, b, t){ return a + (b - a) * t; }

// Movement along Z
let targetZ = camera.position.z;
function moveForward(delta) {
  targetZ = clamp(targetZ - delta, -38, 8);
}
function moveBack(delta) {
  targetZ = clamp(targetZ + delta, -38, 8);
}

// Smooth camera tween
function tweenToDoor(doorMeta) {
  if (!doorMeta) return;
  activeDoor = doorMeta;

  const dz = doorMeta.pivot.position.z;
  const dx = doorMeta.pivot.position.x + (doorMeta.side === "L" ? 1.0 : -1.0);

  // Open more
  doorMeta.pivot.rotation.y = (doorMeta.side === "L") ? 0.55 : -0.55;

  // Tween camera
  const start = {
    x: camera.position.x,
    y: camera.position.y,
    z: camera.position.z,
    yaw,
    pitch
  };
  const end = {
    x: dx,
    y: 1.65,
    z: dz + 2.9,
    yaw: (doorMeta.side === "L") ? 0.28 : -0.28,
    pitch: 0
  };

  const duration = 520;
  const t0 = performance.now();

  function step(now) {
    const t = clamp((now - t0) / duration, 0, 1);
    const ease = t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t+2, 2)/2; // easeInOutQuad

    camera.position.x = lerp(start.x, end.x, ease);
    camera.position.y = lerp(start.y, end.y, ease);
    camera.position.z = lerp(start.z, end.z, ease);
    yaw = lerp(start.yaw, end.yaw, ease);
    pitch = lerp(start.pitch, end.pitch, ease);

    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);

  showTooltip(doorMeta);
}

function showTooltip(meta) {
  doorTitle.textContent = meta.label || "Door";
  doorDesc.textContent = meta.desc || "";
  tooltip.style.display = "block";

  doorEnterBtn.onclick = () => { window.location.href = meta.href; };
  doorCloseBtn.onclick = () => { hideTooltip(); };
}

function hideTooltip() {
  tooltip.style.display = "none";
  activeDoor = null;
}

// ----- Events -----
renderer.domElement.addEventListener("mousemove", (ev) => {
  setPointerFromEvent(ev);
});

renderer.domElement.addEventListener("click", (ev) => {
  setPointerFromEvent(ev);
  const meta = pickDoor();
  if (meta) tweenToDoor(meta);
});

renderer.domElement.addEventListener("touchstart", (ev) => {
  const t = ev.touches[0];
  lastX = t.clientX;
  lastY = t.clientY;
  dragging = true;
}, { passive: true });

renderer.domElement.addEventListener("touchmove", (ev) => {
  if (!dragging) return;
  const t = ev.touches[0];
  const dx = t.clientX - lastX;
  const dy = t.clientY - lastY;
  lastX = t.clientX;
  lastY = t.clientY;

  yaw -= dx * 0.006;
  pitch -= dy * 0.006;
  pitch = clamp(pitch, -0.65, 0.45);
}, { passive: true });

renderer.domElement.addEventListener("touchend", () => {
  dragging = false;
}, { passive: true });

// Desktop drag-to-look
renderer.domElement.addEventListener("mousedown", (ev) => {
  dragging = true;
  lastX = ev.clientX;
  lastY = ev.clientY;
});
window.addEventListener("mouseup", () => dragging = false);
window.addEventListener("mousemove", (ev) => {
  if (!dragging) return;
  const dx = ev.clientX - lastX;
  const dy = ev.clientY - lastY;
  lastX = ev.clientX;
  lastY = ev.clientY;

  yaw -= dx * 0.006;
  pitch -= dy * 0.006;
  pitch = clamp(pitch, -0.65, 0.45);
});

// Wheel to move
renderer.domElement.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const dir = Math.sign(ev.deltaY);
  if (dir > 0) moveForward(1.6);
  else moveBack(1.6);
}, { passive: false });

// Double tap / double click to re-center
let lastTap = 0;
renderer.domElement.addEventListener("touchend", () => {
  const now = Date.now();
  if (now - lastTap < 280) {
    yaw = 0; pitch = 0;
  }
  lastTap = now;
});
renderer.domElement.addEventListener("dblclick", () => {
  yaw = 0; pitch = 0;
});

// Close tooltip if clicking outside it
window.addEventListener("click", (e) => {
  if (!tooltip || tooltip.style.display === "none") return;
  const isInside = tooltip.contains(e.target);
  if (!isInside && e.target !== renderer.domElement) hideTooltip();
});

// Resize
window.addEventListener("resize", () => {
  const w = mount.clientWidth;
  const h = mount.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
});

// ----- Render loop -----
function animate() {
  requestAnimationFrame(animate);

  // Hover detection
  if (!activeDoor) {
    const meta = pickDoor();
    if (meta !== hoveredDoor) {
      // unhighlight old
      if (hoveredDoor) highlightDoor(hoveredDoor, false);
      hoveredDoor = meta;
      if (hoveredDoor) highlightDoor(hoveredDoor, true);
    }
  }

  // Smooth movement forward/back
  camera.position.z = lerp(camera.position.z, targetZ, 0.08);

  // Apply camera look
  const lookTarget = new THREE.Vector3(
    camera.position.x + Math.sin(yaw),
    camera.position.y + pitch,
    camera.position.z - Math.cos(yaw)
  );
  camera.lookAt(lookTarget);

  // Mild breathing light
  runner.material.opacity = 0.12 + 0.03 * Math.sin(performance.now() * 0.0015);

  renderer.render(scene, camera);
}
animate();
