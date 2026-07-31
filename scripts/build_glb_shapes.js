// Build solid GLB shapes with POSITION + NORMAL + indices.
// Uses separate (non-interleaved) buffer views for max compatibility.

const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'data', 'shapes');

// ── GLB binary packer ──────────────────────────────────────────────────────────

function align4(n) { return (n + 3) & ~3; }

function floatsToBuffer(arr) {
  const buf = Buffer.alloc(arr.length * 4);
  for (let i = 0; i < arr.length; i++) buf.writeFloatLE(arr[i], i * 4);
  return buf;
}

function uintsToBuffer(arr) {
  const buf = Buffer.alloc(arr.length * 4);
  for (let i = 0; i < arr.length; i++) buf.writeUInt32LE(arr[i], i * 4);
  return buf;
}

function minMax(arr) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < arr.length; i += 3) {
    for (let j = 0; j < 3; j++) {
      const v = arr[i + j];
      if (v < min[j]) min[j] = v;
      if (v > max[j]) max[j] = v;
    }
  }
  return { min, max };
}

function buildGLB(positions, normals, indices) {
  const vertexCount = positions.length / 3;
  const posBuf = floatsToBuffer(positions);
  const nrmBuf = floatsToBuffer(normals);
  const idxBuf = uintsToBuffer(indices);

  // Layout: [positions] [normals] [indices], each padded to 4-byte alignment
  const posOff = 0;
  const nrmOff = align4(posBuf.length);
  const idxOff = nrmOff + align4(nrmBuf.length);
  const totalBin = idxOff + align4(idxBuf.length);

  const binChunkData = Buffer.alloc(totalBin);
  posBuf.copy(binChunkData, posOff);
  nrmBuf.copy(binChunkData, nrmOff);
  idxBuf.copy(binChunkData, idxOff);

  // Fill padding gaps with 0x00 (not strictly required but clean)
  for (let i = posBuf.length; i < nrmOff; i++) binChunkData[i] = 0;
  for (let i = nrmOff + nrmBuf.length; i < idxOff; i++) binChunkData[i] = 0;

  const json = {
    asset: { version: '2.0', generator: 'dassein-build-glb' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{
      primitives: [{
        attributes: { POSITION: 0, NORMAL: 1 },
        indices: 2,
        mode: 4,
        material: 0,
      }],
    }],
    materials: [{
      pbrMetallicRoughness: { baseColorFactor: [0.8, 0.8, 0.8, 1], metallicFactor: 0.1, roughnessFactor: 0.6 },
      name: 'default',
    }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: vertexCount, type: 'VEC3',
        min: minMax(positions).min, max: minMax(positions).max },
      { bufferView: 1, componentType: 5126, count: vertexCount, type: 'VEC3' },
      { bufferView: 2, componentType: 5125, count: indices.length, type: 'SCALAR' },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: posOff, byteLength: posBuf.length, target: 34962 },
      { buffer: 0, byteOffset: nrmOff, byteLength: nrmBuf.length, target: 34962 },
      { buffer: 0, byteOffset: idxOff, byteLength: idxBuf.length, target: 34963 },
    ],
    buffers: [{ byteLength: totalBin }],
  };

  const jsonStr = JSON.stringify(json);
  const jsonLen = jsonStr.length;
  const jsonPadded = Buffer.alloc(align4(jsonLen));
  jsonPadded.write(jsonStr, 0);

  const totalLen = 12 + 8 + align4(jsonLen) + 8 + totalBin;
  const buf = Buffer.alloc(totalLen);
  let o = 0;
  buf.writeUInt32LE(0x46546C67, o); o += 4; // magic
  buf.writeUInt32LE(2, o);          o += 4; // version
  buf.writeUInt32LE(totalLen, o);   o += 4; // totalLength

  buf.writeUInt32LE(jsonLen, o); o += 4;  // JSON chunk len (exact)
  buf.writeUInt32LE(0x4E4F534A, o);       o += 4;  // JSON chunk type
  jsonPadded.copy(buf, o); o += jsonPadded.length;

  buf.writeUInt32LE(totalBin, o); o += 4;  // BIN chunk len
  buf.writeUInt32LE(0x004E4942, o);        o += 4;  // BIN chunk type
  binChunkData.copy(buf, o);

  return buf;
}

// ── Geometry generators ────────────────────────────────────────────────────────

function vec3(x, y, z) { return [x, y, z]; }
function add(a, b) { return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]; }
function sub(a, b) { return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]; }
function cross(a, b) { return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]; }
function normalize(v) {
  const l = Math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
  return l > 0 ? [v[0]/l, v[1]/l, v[2]/l] : [0,0,0];
}

function buildCube(size = 1.0) {
  const h = size / 2;
  const pos = []; const nrm = []; const idx = [];
  const faces = [
    { v: [[-h,-h, h],[ h,-h, h],[ h, h, h],[-h, h, h]], n: [ 0, 0, 1] },
    { v: [[ h,-h,-h],[-h,-h,-h],[-h, h,-h],[ h, h,-h]], n: [ 0, 0,-1] },
    { v: [[ h,-h, h],[ h,-h,-h],[ h, h,-h],[ h, h, h]], n: [ 1, 0, 0] },
    { v: [[-h,-h,-h],[-h,-h, h],[-h, h, h],[-h, h,-h]], n: [-1, 0, 0] },
    { v: [[-h, h, h],[ h, h, h],[ h, h,-h],[-h, h,-h]], n: [ 0, 1, 0] },
    { v: [[-h,-h,-h],[ h,-h,-h],[ h,-h, h],[-h,-h, h]], n: [ 0,-1, 0] },
  ];
  faces.forEach((face, fi) => {
    const base = fi * 4;
    face.v.forEach(v => { pos.push(...v); nrm.push(...face.n); });
    idx.push(base, base+1, base+2, base, base+2, base+3);
  });
  return { positions: new Float32Array(pos), normals: new Float32Array(nrm), indices: new Uint32Array(idx) };
}

function buildCylinder(radius, height, segs) {
  const h = height / 2;
  const pos = []; const nrm = []; const idx = [];
  for (let i = 0; i < segs; i++) {
    const a = (i / segs) * Math.PI * 2;
    const x = Math.cos(a) * radius, z = Math.sin(a) * radius;
    pos.push(x, h, z);  nrm.push(Math.cos(a), 0, Math.sin(a));
    pos.push(x, -h, z); nrm.push(Math.cos(a), 0, Math.sin(a));
  }
  for (let i = 0; i < segs; i++) {
    const t = i * 2, b = i * 2 + 1;
    const nt = ((i + 1) % segs) * 2, nb = ((i + 1) % segs) * 2 + 1;
    idx.push(t, b, nb, t, nb, nt);
  }
  const topCenter = pos.length / 3; pos.push(0, h, 0); nrm.push(0, 1, 0);
  const topStart = topCenter + 1;
  for (let i = 0; i < segs; i++) {
    const a = (i / segs) * Math.PI * 2;
    pos.push(Math.cos(a) * radius, h, Math.sin(a) * radius); nrm.push(0, 1, 0);
  }
  for (let i = 0; i < segs; i++) {
    idx.push(topCenter, topStart + ((i + 1) % segs), topStart + i);
  }
  const botCenter = pos.length / 3; pos.push(0, -h, 0); nrm.push(0, -1, 0);
  const botStart = botCenter + 1;
  for (let i = 0; i < segs; i++) {
    const a = (i / segs) * Math.PI * 2;
    pos.push(Math.cos(a) * radius, -h, Math.sin(a) * radius); nrm.push(0, -1, 0);
  }
  for (let i = 0; i < segs; i++) {
    idx.push(botCenter, botStart + i, botStart + ((i + 1) % segs));
  }
  return { positions: new Float32Array(pos), normals: new Float32Array(nrm), indices: new Uint32Array(idx) };
}

function buildPyramid(baseHalf, height) {
  const h = height / 2;
  const pos = []; const nrm = []; const idx = [];
  const bv = [[-baseHalf,-h,-baseHalf],[baseHalf,-h,-baseHalf],[baseHalf,-h,baseHalf],[-baseHalf,-h,baseHalf]];
  const apex = [0, h, 0];
  bv.forEach(v => { pos.push(...v); nrm.push(0, -1, 0); });
  idx.push(0, 2, 1, 0, 3, 2);
  for (let i = 0; i < 4; i++) {
    const a = bv[i], b = bv[(i + 1) % 4];
    const fn = normalize(cross(sub(b, a), sub(apex, a)));
    const off = 4 + i * 3;
    pos.push(...a, ...b, ...apex); nrm.push(...fn, ...fn, ...fn);
    idx.push(off, off + 1, off + 2);
  }
  return { positions: new Float32Array(pos), normals: new Float32Array(nrm), indices: new Uint32Array(idx) };
}

function buildSphere(radius, latSegs, lonSegs) {
  const pos = []; const nrm = []; const idx = [];
  for (let lat = 0; lat <= latSegs; lat++) {
    const theta = (lat / latSegs) * Math.PI;
    const sinT = Math.sin(theta), cosT = Math.cos(theta);
    for (let lon = 0; lon <= lonSegs; lon++) {
      const phi = (lon / lonSegs) * Math.PI * 2;
      const sinP = Math.sin(phi), cosP = Math.cos(phi);
      pos.push(cosP * sinT * radius, cosT * radius, sinP * sinT * radius);
      nrm.push(cosP * sinT, cosT, sinP * sinT);
    }
  }
  const cols = lonSegs + 1;
  for (let lat = 0; lat < latSegs; lat++) {
    for (let lon = 0; lon < lonSegs; lon++) {
      const a = lat * cols + lon, b = a + cols, c = a + 1, d = b + 1;
      idx.push(a, b, c, c, b, d);
    }
  }
  return { positions: new Float32Array(pos), normals: new Float32Array(nrm), indices: new Uint32Array(idx) };
}

function buildTorus(majorR, minorR, majorSegs, minorSegs) {
  const pos = []; const nrm = []; const idx = [];
  for (let i = 0; i <= majorSegs; i++) {
    const theta = (i / majorSegs) * Math.PI * 2;
    const cosT = Math.cos(theta), sinT = Math.sin(theta);
    for (let j = 0; j <= minorSegs; j++) {
      const phi = (j / minorSegs) * Math.PI * 2;
      const cosP = Math.cos(phi), sinP = Math.sin(phi);
      const r = majorR + minorR * cosP;
      pos.push(cosT * r, sinT * r, minorR * sinP);
      nrm.push(cosT * cosP, sinT * cosP, sinP);
    }
  }
  const cols = minorSegs + 1;
  for (let i = 0; i < majorSegs; i++) {
    for (let j = 0; j < minorSegs; j++) {
      const a = i * cols + j, b = a + cols, c = a + 1, d = b + 1;
      idx.push(a, b, c, c, b, d);
    }
  }
  return { positions: new Float32Array(pos), normals: new Float32Array(nrm), indices: new Uint32Array(idx) };
}

// ── Main ────────────────────────────────────────────────────────────────────────

const shapes = {
  cube:     buildCube(0.5),
  cylinder: buildCylinder(0.5, 1.0, 48),
  pyramid:  buildPyramid(0.5, 0.85),
  sphere:   buildSphere(0.5, 48, 48),
  torus:    buildTorus(0.45, 0.18, 64, 32),
};

fs.mkdirSync(OUT, { recursive: true });

for (const [name, geo] of Object.entries(shapes)) {
  const glb = buildGLB(geo.positions, geo.normals, geo.indices);
  const outPath = path.join(OUT, name + '.glb');
  fs.writeFileSync(outPath, glb);
  console.log(`Wrote ${outPath} (${glb.length} bytes, ${geo.positions.length/3} verts, ${geo.indices.length/3} tris)`);
}

console.log('Done.');
