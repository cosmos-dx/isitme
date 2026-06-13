// Generates the extension PNG icons at build time so no binary assets live in
// source control. Pure Node (zlib only) — a tiny PNG encoder draws a simple
// "knowledge-graph orb": a dark tile with an accent node and a few satellites.
import zlib from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const body = Buffer.concat([typeBuf, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}

function encodePng(size, pixels /* Uint8Array RGBA size*size*4 */) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  // raw scanlines, filter byte 0 per row
  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0;
    pixels.subarray(y * stride, y * stride + stride).forEach((v, i) => {
      raw[y * (stride + 1) + 1 + i] = v;
    });
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", idat),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const BG = [11, 11, 20]; // #0b0b14
const ACCENT = [124, 92, 255]; // #7c5cff
const CYAN = [34, 211, 238]; // #22d3ee
const GREEN = [52, 211, 153]; // #34d399

function lerp(a, b, t) {
  return Math.round(a + (b - a) * t);
}

function drawIcon(size) {
  const px = new Uint8Array(size * size * 4);
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.42;
  // satellite nodes (normalized positions + color + radius factor)
  const sats = [
    { x: 0.22, y: 0.26, c: CYAN, rf: 0.1 },
    { x: 0.8, y: 0.32, c: GREEN, rf: 0.09 },
    { x: 0.74, y: 0.78, c: CYAN, rf: 0.08 },
    { x: 0.26, y: 0.76, c: GREEN, rf: 0.08 },
  ];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      let rr = BG[0];
      let gg = BG[1];
      let bb = BG[2];
      // central orb with radial gradient
      const d = Math.hypot(x - cx, y - cy);
      if (d < r) {
        const t = d / r;
        rr = lerp(ACCENT[0], BG[0], t * 0.85);
        gg = lerp(ACCENT[1], BG[1], t * 0.85);
        bb = lerp(ACCENT[2], BG[2], t * 0.6);
      }
      // satellites + connecting lines
      for (const s of sats) {
        const sxp = s.x * size;
        const syp = s.y * size;
        const sr = size * s.rf;
        const sd = Math.hypot(x - sxp, y - syp);
        if (sd < sr) {
          rr = s.c[0];
          gg = s.c[1];
          bb = s.c[2];
        }
        // thin line toward center
        const lineD = distToSegment(x, y, sxp, syp, cx, cy);
        if (lineD < size * 0.012 && d > r * 0.6) {
          rr = lerp(rr, s.c[0], 0.4);
          gg = lerp(gg, s.c[1], 0.4);
          bb = lerp(bb, s.c[2], 0.4);
        }
      }
      px[i] = rr;
      px[i + 1] = gg;
      px[i + 2] = bb;
      px[i + 3] = 255;
    }
  }
  return encodePng(size, px);
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy || 1;
  let t = ((px - ax) * dx + (py - ay) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function generateIcons(outDir) {
  for (const size of [16, 32, 48, 128]) {
    const file = `${outDir}/icon-${size}.png`;
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, drawIcon(size));
  }
}

// allow `node scripts/gen-icons.mjs <outDir>`
if (import.meta.url === `file://${process.argv[1]}`) {
  generateIcons(process.argv[2] || "dist/icons");
  console.log("icons generated");
}
