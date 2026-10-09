// Runs the page's real static/js/suit.js in node on a fake VRM and checks
// how tintUndersuit dresses the skin: the light suit's shorts band, the full
// suit's undersuit, and the covers it must refuse or warn about. Three comes
// from the Forge shared vendor folder (FORGE_SHARED_DIR, as the app); the
// loaders suit.js imports for real files are stubs. Prints "ok N" and exits
// 0 when every check holds, else names each failed one on stderr;
// tests/test_suit_js.py runs it.
import { registerHooks } from "node:module";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const shared = process.env.FORGE_SHARED_DIR
  ? pathToFileURL(`${process.env.FORGE_SHARED_DIR}/`)
  : new URL("../../../../shared/", import.meta.url);
const stub = (code) => `data:text/javascript,${encodeURIComponent(code)}`;
const STUBS = {
  three: new URL("vendor/three/three.module.min.js", shared).href,
  "three/addons/loaders/GLTFLoader.js": stub("export class GLTFLoader { register() {} loadAsync() {} }"),
  "three-vrm": stub("export class VRMLoaderPlugin {} export const VRMUtils = {};"),
};
registerHooks({
  resolve(specifier, context, next) {
    if (STUBS[specifier]) return { url: STUBS[specifier], format: "module", shortCircuit: true };
    const got = next(specifier, context);
    return got.url.endsWith(".js") ? { ...got, format: "module" } : got;
  },
});
const { tintUndersuit, THREE } = await import("../../static/js/suit.js");

const warns = [];
console.warn = (...a) => warns.push(a.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" "));

// root -> hips (at hipsY) -> leftUpperLeg; one skinned Body mesh of small
// triangles whose centres sit just above the heights ys, weighted to hips.
function fakeVrm({ ys, hipsY = 1.0, mats = ["Body_00_SKIN"], groups = null, indexed = true, hipsInSkeleton = true }) {
  const scene = new THREE.Group();
  const root = new THREE.Bone();
  const hips = new THREE.Bone();
  hips.name = "J_Bip_C_Hips";
  hips.position.y = hipsY;
  const leg = new THREE.Bone();
  leg.position.y = -0.1;
  root.add(hips);
  hips.add(leg);
  scene.add(root);
  scene.updateMatrixWorld(true);
  const pos = [];
  const si = [];
  const sw = [];
  const idx = [];
  ys.forEach((y, f) => {
    for (const dx of [0, 0.01, 0.02]) {
      pos.push(f * 0.03 + dx, y + (dx === 0.01 ? 0.005 : 0), 0);
      si.push(1, 0, 0, 0);
      sw.push(1, 0, 0, 0);
    }
    idx.push(3 * f, 3 * f + 1, 3 * f + 2);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(si, 4));
  g.setAttribute("skinWeight", new THREE.Float32BufferAttribute(sw, 4));
  if (indexed) g.setIndex(idx);
  if (groups) for (const [s, c, mi] of groups) g.addGroup(s, c, mi);
  const ms = mats.map((n) => Object.assign(new THREE.MeshBasicMaterial({ color: 0xffccaa }), { name: n }));
  const mesh = new THREE.SkinnedMesh(g, ms.length > 1 ? ms : ms[0]);
  mesh.name = "Body";
  scene.add(mesh);
  mesh.bind(new THREE.Skeleton(hipsInSkeleton ? [root, hips, leg] : [root, leg]), new THREE.Matrix4());
  const humanoid = { getRawBoneNode: (n) => ({ hips, leftUpperLeg: leg })[n] ?? null };
  return { scene, humanoid, mesh, ms };
}

const skinned = (v) => {
  const out = [];
  v.scene.traverse((o) => o.isSkinnedMesh && out.push(o));
  return out;
};
const twinOf = (v) => skinned(v).find((m) => m.name === "Body_shorts");
// Hips at 1.0 and a band from -0.26 to 0.075 m: 0.74 to 1.075 m, so four of
// these fifteen faces (0.739, 0.745, 0.8 and 1.07, centres 1.7 mm higher).
const YS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.739, 0.745, 0.8, 1.07, 1.08, 1.2, 1.3, 1.4, 1.5];
const LITE = { undersuit: false, cover: { bone: "hips", from_m: -0.26, to_m: 0.075 } };
const cover = (c) => ({ skin: { undersuit: false, cover: { bone: "hips", ...c } } });
let checks = 0;
const failed = [];
const check = (fn, what) => {
  warns.length = 0;
  try {
    fn();
    checks += 1;
  } catch (err) {
    failed.push(`${what}: ${err.message.split("\n")[0]}`);
  }
};

check(() => {
  const v = fakeVrm({ ys: YS });
  assert.equal(tintUndersuit(v, { skin: LITE }), false);
  assert.equal(v.scene.userData.exolabSkin.shorts, 4);
  const twin = twinOf(v);
  assert.ok(twin, "a shorts twin");
  assert.equal(twin.geometry.index.count / 3, 4);
  assert.equal(v.mesh.geometry.index.count / 3, 11);
  assert.equal(twin.geometry.attributes.position, v.mesh.geometry.attributes.position);
  assert.equal(twin.skeleton, v.mesh.skeleton);
  assert.notEqual(twin.material.color.getHexString(), v.ms[0].color.getHexString());
  assert.deepEqual(warns, []);
  // A second call gives the first answer and adds no second twin.
  assert.equal(tintUndersuit(v, { skin: LITE }), false);
  assert.equal(skinned(v).length, 2);
}, "light suit shorts");

check(() => {
  const v = fakeVrm({ ys: YS });
  assert.equal(tintUndersuit(v, { skin: { undersuit: true } }), true);
  assert.ok(v.ms[0].color.getHSL({}).l < 0.2, "the skin went dark");
  assert.equal(twinOf(v), undefined);
}, "full suit undersuit");

check(() => {
  // MToon draws each skin face twice (the skin and its outline material):
  // the count is of faces, not draws.
  const n = YS.length * 3;
  const v = fakeVrm({ ys: YS, mats: ["Body_00_SKIN", "Body_00_SKIN (Outline)"], groups: [[0, n, 0], [0, n, 1]] });
  tintUndersuit(v, { skin: LITE });
  assert.equal(v.scene.userData.exolabSkin.shorts, 4);
  assert.equal(twinOf(v).geometry.index.count / 3, 8);
}, "outline pair counted once");

for (const [bad, what] of [
  [{ from_m: null, to_m: 0.075 }, "from_m null"],
  [{ from_m: "-0.26", to_m: 0.075 }, "from_m as text"],
  [{ from_m: -260, to_m: 75 }, "band typed in mm"],
  [{ from_m: 0.075, to_m: -0.26 }, "from_m above to_m"],
  [{ bone: "nope", from_m: -0.26, to_m: 0.075 }, "no such bone"],
]) {
  check(() => {
    const v = fakeVrm({ ys: YS });
    tintUndersuit(v, cover(bad));
    assert.equal(v.scene.userData.exolabSkin.shorts, 0);
    assert.equal(twinOf(v), undefined);
    assert.equal(warns.length, 1);
    assert.match(warns[0], /no shorts: the cover needs a body bone/);
  }, `refuses ${what}`);
}

check(() => {
  const v = fakeVrm({ ys: YS.map((y) => y + 5) });
  tintUndersuit(v, { skin: LITE });
  assert.equal(v.scene.userData.exolabSkin.shorts, 0);
  assert.equal(warns.length, 1);
  assert.match(warns[0], /no skin face lies from -0.26 to 0.075 m about J_Bip_C_Hips/);
}, "a band that misses every face");

check(() => {
  const v = fakeVrm({ ys: YS });
  tintUndersuit(v, cover({ from_m: -1, to_m: 1 }));
  assert.equal(v.scene.userData.exolabSkin.shorts, 15);
  assert.equal(warns.length, 1);
  assert.match(warns[0], /take 15 of 15 skin faces, more than half/);
}, "a band over most of the skin");

// A mesh the band cannot be tried on says why, once: no second warning
// blaming the band.
for (const [opts, says, what] of [
  [{ hipsInSkeleton: false }, /J_Bip_C_Hips is not in its skeleton/, "cover bone not in the skeleton"],
  [{ indexed: false }, /the mesh has no face list/, "a mesh with no face list"],
]) {
  check(() => {
    const v = fakeVrm({ ys: YS, ...opts });
    tintUndersuit(v, { skin: LITE });
    assert.equal(v.scene.userData.exolabSkin.shorts, 0);
    assert.equal(warns.length, 1, JSON.stringify(warns));
    assert.match(warns[0], says);
  }, what);
}

// The closed-helmet pilot: face and hair hidden, a helmet on the head bone.
function headVrm({ withHead = true } = {}) {
  const v = fakeVrm({ ys: YS });
  const head = new THREE.Bone();
  head.position.y = 0.5;
  v.scene.children[0].children[0].add(head);
  const part = (name, mat, y) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.18, 0.12), Object.assign(new THREE.MeshBasicMaterial(), { name: mat }));
    m.name = name;
    m.position.y = y;
    v.scene.add(m);
    return m;
  };
  const parts = [
    part("Face", "F00_000_00_Face_00_SKIN", 1.6),
    part("Eye", "F00_000_00_EyeIris_00_EYE", 1.62),
    part("Hair", "F00_000_Hair_00_HAIR_01", 1.65),
  ];
  v.scene.updateMatrixWorld(true);
  v.humanoid = { getRawBoneNode: (n) => ({ head: withHead ? head : null })[n] ?? null };
  return { v, head, parts };
}

check(() => {
  const { v, head, parts } = headVrm();
  tintUndersuit(v, { skin: { undersuit: true, closed_helmet: true } });
  assert.equal(v.scene.userData.exolabSkin.helmet, 3);
  assert.ok(parts.every((m) => !m.visible));
  assert.ok(v.mesh.visible, "the body stays");
  const helmet = head.children.find((o) => o.name === "exolab_helmet");
  assert.ok(helmet, "a helmet on the head bone");
  const at = helmet.getWorldPosition(new THREE.Vector3());
  assert.ok(Math.abs(at.y - 1.6) < 0.05 && at.z < 0, `helmet round the face, a little behind: ${at.toArray()}`);
  const box = new THREE.Box3().setFromObject(helmet);
  assert.ok(box.getSize(new THREE.Vector3()).x > 0.15, "wider than the face");
  assert.equal(warns.length, 0);
}, "the closed helmet hides the face and hair and sits on the head bone");

check(() => {
  const { v, parts } = headVrm({ withHead: false });
  tintUndersuit(v, { skin: { undersuit: true, closed_helmet: true } });
  assert.equal(v.scene.userData.exolabSkin.helmet, 0);
  assert.ok(parts.every((m) => m.visible), "nothing hidden without a helmet to cover it");
  assert.equal(warns.length, 1);
  assert.match(warns[0], /no closed helmet/);
}, "no head bone, no helmet");

check(() => {
  const { v, parts } = headVrm();
  tintUndersuit(v, { skin: { undersuit: true } });
  assert.equal(v.scene.userData.exolabSkin.helmet, undefined);
  assert.ok(parts.every((m) => m.visible));
}, "no closed_helmet field, face and hair stay");

if (failed.length) {
  console.error(failed.join("\n"));
  process.exit(1);
}
console.log(`ok ${checks}`);
