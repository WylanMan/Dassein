import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const stage = document.getElementById("model-stage");

if (!stage) {
  throw new Error("Missing #model-stage element");
}

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(42, stage.clientWidth / stage.clientHeight, 0.1, 100);
camera.position.set(0, 4.8, 5.8);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(stage.clientWidth, stage.clientHeight);
renderer.setClearColor(0x000000, 0);
stage.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 3.3;
controls.maxDistance = 11;
controls.maxPolarAngle = Math.PI * 0.48;
controls.target.set(0, 0, 0);

const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(10, 1.2, 2);
scene.add(key);

const rim = new THREE.DirectionalLight(0x9bd6ff, 0.55);
rim.position.set(-8, 1.1, -3);
scene.add(rim);

const fill = new THREE.AmbientLight(0x5f5f5f, 0.38);
scene.add(fill);

const trayMaterial = new THREE.MeshStandardMaterial({
  color: 0xededed,
  roughness: 0.42,
  metalness: 0.24,
});

const trayGroup = new THREE.Group();
scene.add(trayGroup);
const WORLD_X = new THREE.Vector3(1, 0, 0);

function orientTrayFlat(mesh, geometrySize) {
  const dims = [
    { axis: "x", value: geometrySize.x },
    { axis: "y", value: geometrySize.y },
    { axis: "z", value: geometrySize.z },
  ].sort((a, b) => a.value - b.value);

  const thinnestAxis = dims[0].axis;

  if (thinnestAxis === "x") {
    mesh.rotation.z = Math.PI / 2;
  } else if (thinnestAxis === "z") {
    mesh.rotation.x = -Math.PI / 2;
  }

  mesh.updateMatrixWorld(true);
  const orientedBox = new THREE.Box3().setFromObject(mesh);
  const orientedSize = orientedBox.getSize(new THREE.Vector3());

  if (orientedSize.z > orientedSize.x) {
    mesh.rotation.y += Math.PI / 2;
  }
}

function ensureFlatSideDown(mesh, geometry) {
  mesh.updateMatrixWorld(true);

  const positions = geometry.attributes.position;
  const sample = new THREE.Vector3();
  let minY = Infinity;
  let maxY = -Infinity;

  for (let i = 0; i < positions.count; i += 1) {
    sample.fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld);
    if (sample.y < minY) minY = sample.y;
    if (sample.y > maxY) maxY = sample.y;
  }

  const thickness = Math.max(maxY - minY, 1e-6);
  const epsilon = thickness * 0.01;
  let nearBottom = 0;
  let nearTop = 0;

  for (let i = 0; i < positions.count; i += 1) {
    sample.fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld);
    if (Math.abs(sample.y - minY) <= epsilon) nearBottom += 1;
    if (Math.abs(sample.y - maxY) <= epsilon) nearTop += 1;
  }

  // If the flatter face is currently on top, flip so it becomes the underside.
  if (nearTop > nearBottom) {
    mesh.rotateX(Math.PI);
  }
}

const loader = new STLLoader();
loader.load(
  "./chinese-tea-tray.stl",
  (geometry) => {
    geometry.computeVertexNormals();
    geometry.center();

    const bounds = new THREE.Box3().setFromBufferAttribute(geometry.attributes.position);
    const size = bounds.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z) || 1;
    const targetSize = 5.8;
    const scale = targetSize / maxDimension;

    const trayMesh = new THREE.Mesh(geometry, trayMaterial);
    trayMesh.scale.setScalar(scale);
    orientTrayFlat(trayMesh, size);
    ensureFlatSideDown(trayMesh, geometry);
    trayMesh.rotateOnWorldAxis(WORLD_X, Math.PI);
    trayMesh.castShadow = false;
    trayMesh.receiveShadow = false;
    trayGroup.add(trayMesh);
  },
  undefined,
  (error) => {
    console.error("Failed to load STL model:", error);
  }
);

function animate() {
  requestAnimationFrame(animate);

  controls.update();
  renderer.render(scene, camera);
}

animate();

window.addEventListener("resize", () => {
  const w = stage.clientWidth;
  const h = stage.clientHeight;

  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
});
