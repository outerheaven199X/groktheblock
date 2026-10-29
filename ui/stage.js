// Grok Bot 3D stage (three.js r164, vendored locally). Falls back to a static bot when WebGL or the modules are unavailable.
const wrap = document.getElementById("stageWrap"), el = document.getElementById("stage");
const RM = matchMedia("(prefers-reduced-motion: reduce)");
function fallback(why) {
  wrap.classList.add("stage-static"); el.dataset.webgl = "fallback"; el.dataset.reason = why;
  document.getElementById("fbNote").textContent = "Static view · " + why;
  const bot = document.getElementById("fbBot");
  const place = () => { const home = window.GTB && window.GTB.S.view === "home"; const w = wrap.clientWidth, h = wrap.clientHeight; bot.style.left = (w >= 640 ? (home ? w * 0.72 : w * 0.25) : w / 2) - 75 + "px"; bot.style.top = Math.max(40, h * 0.42 - 75) + "px"; };
  place(); addEventListener("resize", place); setInterval(place, 500);
  const noop = () => {}; window.GTB_STAGE = { intro: noop, hop: noop, spin: noop, punch: noop, setMode: place, react: noop, set: noop, setTalking: noop, resize: place, setVisible: noop, static: true };
}
function webglOK() { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; } }
async function init() {
  if (new URLSearchParams(location.search).has("nowebgl") || !webglOK()) return fallback("WebGL unavailable");
  let THREE, PP = null;
  try { THREE = await import("three"); } catch (e) { return fallback("3D module failed to load"); }
  try {
    const [a, b, c, d, f] = await Promise.all(["EffectComposer", "RenderPass", "AfterimagePass", "UnrealBloomPass", "OutputPass"].map(n => import("three/addons/postprocessing/" + n + ".js")));
    PP = { ...a, ...b, ...c, ...d, ...f };
  } catch (e) { console.warn("post fx unavailable:", e && e.message); }
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); } catch (e) { return fallback("WebGL context failed"); }
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.1;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  el.appendChild(renderer.domElement); el.dataset.webgl = "ok";
  const scene = new THREE.Scene(); const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
  const camBase = new THREE.Vector3(0, 1.7, 8.4); camera.position.copy(camBase); camera.lookAt(0, 1.75, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x0b0b0d, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-3.5, 5, 4); key.castShadow = true; key.shadow.mapSize.set(1024, 1024); Object.assign(key.shadow.camera, { left: -3, right: 3, top: 3, bottom: -3, near: 1, far: 20 }); key.shadow.radius = 6; key.shadow.bias = -0.0005; scene.add(key);
  const rim = new THREE.DirectionalLight(0x6584f8, 0.8); rim.position.set(4, 2.5, -3); scene.add(rim);
  const fillL = new THREE.DirectionalLight(0xffffff, 0.35); fillL.position.set(-4, -1, 2); scene.add(fillL);
  const tc = document.createElement("canvas"); tc.width = tc.height = 256; const tx = tc.getContext("2d");
  tx.fillStyle = "#5a5a62"; tx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) { tx.fillStyle = (i + j) % 2 ? "#6a6a72" : "#72727a"; tx.fillRect(i * 128 + 3, j * 128 + 3, 122, 122); }
  const floorTex = new THREE.CanvasTexture(tc); floorTex.colorSpace = THREE.SRGBColorSpace; floorTex.wrapS = floorTex.wrapT = THREE.RepeatWrapping; floorTex.repeat.set(24, 24); floorTex.anisotropy = 8;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(48, 48), new THREE.MeshLambertMaterial({ map: floorTex })); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
  scene.fog = new THREE.Fog(0x6a6a72, 9, 26); scene.background = new THREE.Color(0x6a6a72);
  const world = new THREE.Group(); scene.add(world);
  [[-9, -16, 1.6, 7], [-4.5, -21, 2.2, 10], [1.5, -18, 1.2, 5.5], [6, -23, 2.6, 12], [10, -17, 1.4, 6.5], [-13, -24, 2.4, 9], [14, -25, 2, 8]].forEach(([x, z, w, h]) => { const g = new THREE.BoxGeometry(w, h, w); const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ color: 0x5c5c64 })); m.position.set(x, h / 2, z); world.add(m); const e = new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.22 })); e.position.copy(m.position); world.add(e); });
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const cars = [];
  for (let i = 0; i < 22; i++) {
    const zl = i % 3 === 0, dir = rnd() < 0.5 ? -1 : 1, c = i % 4 === 0 ? 0xffffff : 0x00e5ff, len = 0.38 + rnd() * 0.34, g = new THREE.BoxGeometry(len, len, len);
    const fill = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.05, depthWrite: false }));
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: 0.4 }));
    const tl = 2.2 + rnd() * 1.6, tail = zl ? [0, 0, -dir * len / 2, 0, 0, -dir * (len / 2 + tl)] : [-dir * len / 2, 0, 0, -dir * (len / 2 + tl), 0, 0];
    const tg = new THREE.BufferGeometry(); tg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(tail), 3));
    const streak = new THREE.Line(tg, new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: 0.2 }));
    const grp = new THREE.Group(); grp.add(fill, edge, streak);
    if (zl) grp.position.set((rnd() < 0.5 ? -1 : 1) * (3 + rnd() * 5), 2.7 + rnd() * 1.9, -20 + rnd() * 22); else grp.position.set(-13 + rnd() * 26, 2.6 + rnd() * 2.6, -3 - rnd() * 10);
    world.add(grp); cars.push({ grp, fill, edge, streak, zl, dir, v: 0.004 + rnd() * 0.005 });
  }
  const root = new THREE.Group(); root.scale.setScalar(1.35); scene.add(root);
  const squash = new THREE.Group(); root.add(squash);
  const body = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), new THREE.MeshStandardMaterial({ color: 0x141418, roughness: 0.62, metalness: 0 }));
  body.position.y = 1; body.castShadow = true; squash.add(body);
  const eyePivot = new THREE.Group(); eyePivot.position.y = 1; squash.add(eyePivot);
  const eyeMat = new THREE.MeshBasicMaterial({ color: 0xf8f8fa });
  const eyes = [[-0.31, 0.04], [0.31, 0.04]].map(([x, y]) => {
    const n = new THREE.Vector3(x, y, Math.sqrt(Math.max(0, 1 - x * x - y * y))).normalize();
    const holder = new THREE.Group(); holder.position.copy(n.clone().multiplyScalar(0.995)); holder.lookAt(n.clone().multiplyScalar(3)); eyePivot.add(holder);
    const tilt = new THREE.Group(); holder.add(tilt);
    const m = new THREE.Mesh(new THREE.CapsuleGeometry(0.12, 0.32, 10, 20), eyeMat); m.scale.z = 0.25; tilt.add(m); return tilt;
  });
  let composer = null;
  if (PP) { try { composer = new PP.EffectComposer(renderer); composer.addPass(new PP.RenderPass(scene, camera)); composer.addPass(new PP.AfterimagePass(0.72)); composer.addPass(new PP.UnrealBloomPass(new THREE.Vector2(512, 512), 0.28, 0.4, 0.86)); composer.addPass(new PP.OutputPass()); } catch (e) { composer = null; } }
  el.dataset.post = composer ? "on" : "off";
  let lastW = 0, lastH = 0;
  const resize = () => { const w = el.clientWidth, h = el.clientHeight; if (!w || !h || (w === lastW && h === lastH)) return; lastW = w; lastH = h; renderer.setSize(w, h, false); if (composer) composer.setSize(w, h); camera.aspect = w / h; camBase.z = w / h < 1 ? 11 : 8.4; camera.position.z = camBase.z; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(el); resize();
  let mode = "home", rotY = 0, drag = null, look = { x: 0, y: 0 }, lookT = { x: -0.45, y: -0.05 };
  const gaze = () => mode === "home" ? { x: -0.5, y: -0.05 } : { x: 0.3, y: -0.05 };
  el.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, ry: rotY }; el.style.cursor = "grabbing"; });
  addEventListener("pointermove", (e) => { const r = wrap.getBoundingClientRect(); if (drag) rotY = drag.ry + (e.clientX - drag.x) * 0.01; if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) lookT = { x: ((e.clientX - r.left) / r.width - 0.5) * 1.4, y: -((e.clientY - r.top) / r.height - 0.5) * 0.9 }; });
  addEventListener("pointerup", () => { drag = null; el.style.cursor = "grab"; });
  wrap.addEventListener("pointerleave", () => { lookT = gaze(); });
  const acts = [], now0 = () => performance.now();
  const add = (type, dur, delay = 0) => { if (RM.matches && type !== "blink") return; acts.push({ type, t0: now0() + delay, dur }); };
  const EMO = ["happy", "suspicious", "surprised", "worried", "determined"]; let emo = null, emoI = 0, nextEmo = now0() + 3200, nextBlink = now0() + 2500, talking = false, curX = null, visible = true;
  const api = {
    intro: () => { acts.length = 0; add("drop", 1150); add("blink", 180, 1300); },
    hop: () => { add("hop", 420); lookT = { x: 0.6, y: -0.02 }; }, spin: () => add("spin", 900), punch: () => add("punch", 380),
    setMode: (m) => { if (m !== mode) add("hop", 420); mode = m; lookT = gaze(); },
    react: (vc) => { if (vc === "red") { add("shake", 700); add("blink", 180, 800); } else add("tilt", 900); lookT = gaze(); },
    set: () => add("hop", 420), setTalking: (v) => { talking = v; }, resize, setVisible: (v) => { visible = v; }, static: false,
  };
  api.intro();
  const easeIO = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  const bounce = (x) => { const n1 = 7.5625, d1 = 2.75; if (x < 1 / d1) return n1 * x * x; if (x < 2 / d1) return n1 * (x -= 1.5 / d1) * x + 0.75; if (x < 2.5 / d1) return n1 * (x -= 2.25 / d1) * x + 0.9375; return n1 * (x -= 2.625 / d1) * x + 0.984375; };
  let frames = 0;
  const step = (now) => {
    resize(); const still = RM.matches; const tt = still ? 0 : now;
    let y = 0, sx = 1, sy = 1, rz = 0, ry = 0, ox = 0, eyeS = 1, fk = 0;
    for (let i = acts.length - 1; i >= 0; i--) {
      const a = acts[i], p = (now - a.t0) / a.dur; if (p < 0) continue; if (p > 1) { acts.splice(i, 1); continue; }
      if (a.type === "drop") { y += (1 - bounce(p)) * 5; const land = Math.max(0, 1 - Math.abs(p - 0.36) * 12) + Math.max(0, 1 - Math.abs(p - 0.73) * 16) * 0.5; sy *= 1 - land * 0.22; sx *= 1 + land * 0.16; }
      if (a.type === "hop") { y += Math.sin(Math.PI * p) * 0.32; const sq = Math.max(0, 1 - p * 6) + Math.max(0, 1 - (1 - p) * 6); sy *= 1 - sq * 0.12; sx *= 1 + sq * 0.08; }
      if (a.type === "spin") { ry += easeIO(p) * Math.PI * 2; y += Math.sin(Math.PI * p) * 0.25; }
      if (a.type === "shake") { rz += Math.sin(p * Math.PI * 7) * 0.16 * (1 - p); ox += Math.sin(p * Math.PI * 9) * 0.08 * (1 - p); }
      if (a.type === "tilt") rz += Math.sin(Math.PI * p) * 0.28;
      if (a.type === "blink") eyeS = Math.min(eyeS, Math.abs(Math.cos(Math.PI * p)) * 0.9 + 0.1);
      if (a.type === "punch") fk += Math.sin(Math.PI * p) * 4.5;
    }
    camera.fov = 28 - fk; camera.updateProjectionMatrix();
    if (!still) {
      floorTex.offset.y = (now * 0.00012) % 1;
      cars.forEach(c => { const p = c.grp.position; let f; if (c.zl) { p.z += c.v * c.dir * 1.3; if (p.z > 3) p.z = -20; if (p.z < -20) p.z = 3; f = Math.min(1, Math.max(0, (p.z + 20) / 5)) * Math.min(1, Math.max(0, (3 - p.z) / 3)); } else { p.x += c.v * c.dir; if (p.x > 13) p.x = -13; if (p.x < -13) p.x = 13; f = Math.min(1, Math.max(0, (13 - Math.abs(p.x)) / 3.5)); } p.y += Math.sin(now * 0.0004 + p.x) * 0.0006; c.edge.material.opacity = 0.42 * f; c.fill.material.opacity = 0.06 * f; c.streak.material.opacity = 0.22 * f; });
      if (now > nextBlink) { add("blink", 170); nextBlink = now + 2600 + Math.random() * 2600; }
      if (talking) { const tk = Math.sin(now * 0.03) * 0.035; sy *= 1 + tk; sx *= 1 - tk * 0.5; }
      if (now > nextEmo) { emo = { k: EMO[emoI++ % EMO.length], t0: now }; nextEmo = now + 5000; if (emo.k === "happy" || emo.k === "surprised") add("hop", 380); }
    }
    const idle = still ? 0 : Math.sin(now * 0.0021) * 0.05;
    const botT = camera.aspect >= 1.25 ? (mode === "home" ? 2.2 : -2.0) : 0; if (curX == null || still) curX = botT; curX += (botT - curX) * 0.04;
    const hx = curX + (still ? 0 : Math.sin(now * 0.00055) * 0.3), hy = 0.95 + (still ? 0 : Math.sin(now * 0.0011) * 0.12);
    root.position.set(ox + hx, y + hy + idle, still ? 0 : Math.sin(now * 0.0004) * 0.3);
    rz += still ? 0 : -Math.cos(now * 0.00055) * 0.09;
    let ew = 0; if (emo && !still) { const q = (now - emo.t0) / 1100; ew = q < 0 || q > 1 ? 0 : Math.max(0, Math.min(1, q / 0.15, (1 - q) / 0.2)); }
    if (emo && emo.k === "suspicious") rz += 0.12 * ew; if (emo && emo.k === "worried") sy *= 1 - 0.05 * ew;
    squash.scale.set(sx, sy, sx); root.rotation.set(0, rotY + ry + (still ? 0 : Math.sin(tt * 0.0007) * 0.05), rz);
    look.x += (lookT.x - look.x) * (still ? 1 : 0.08); look.y += (lookT.y - look.y) * (still ? 1 : 0.08); eyePivot.rotation.set(-look.y * 0.5, look.x * 0.6, 0);
    eyes.forEach((e, i) => { let ey = eyeS, ex = 1, rot = i === 0 ? 0.03 : -0.03, py = 0; const k = emo && ew > 0 ? emo.k : null;
      if (k === "happy") { ey *= 1 - 0.6 * ew; py = 0.03 * ew; } if (k === "surprised") { ey *= 1 + 0.3 * ew; ex = 1 + 0.3 * ew; } if (k === "suspicious") ey *= 1 - (i === 0 ? 0.65 : 0.25) * ew;
      if (k === "worried") rot += (i === 0 ? -0.45 : 0.45) * ew; if (k === "determined") { rot += (i === 0 ? 0.45 : -0.45) * ew; ey *= 1 - 0.2 * ew; }
      e.scale.set(ex, ey, 1); e.rotation.z = rot; e.position.y = py; });
    key.shadow.radius = 6 + Math.max(0, root.position.y) * 4; if (!drag) rotY += (0 - rotY) * 0.01;
    if (composer && !still) composer.render(); else renderer.render(scene, camera);
    el.dataset.frames = ++frames;
  };
  let failed = false;
  const loop = (now) => { requestAnimationFrame(loop); if (failed || !visible || document.hidden) return; try { step(now); } catch (e) { failed = true; console.warn("stage frame:", e && e.message); fallback("render error"); renderer.domElement.remove(); } };
  requestAnimationFrame(loop);
  window.GTB_STAGE = api;
  if (window.GTB) api.setMode(window.GTB.S.view === "home" ? "home" : "result");
}
init();
