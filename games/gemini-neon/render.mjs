#!/usr/bin/env node
// Gemini Neon frame-exact renderer.
// Steps the game at a fixed timestep in headless Chromium and writes every frame at 1080x1920,
// so the result has a constant frame rate with no dropped frames (After Effects friendly).
//
//   node render.mjs                                   # 12 s, 60 fps, film-mode auto direction -> out/gemini-neon.mp4
//   node render.mjs --seconds 15 --fps 30 --shots "low:3,chase:4,side:3,top:3,front:2"
//   node render.mjs --png --out out/frames            # PNG sequence only (import as an image sequence in AE)
//   node render.mjs --headed                          # use the real GPU through a visible browser window
//
// Options
//   --seconds N    clip length (default 12)
//   --fps N        frame rate (default 60)
//   --seed N       gameplay seed (default 20261122)
//   --shots LIST   camera timeline "shot:seconds,..." with hard cuts; shots: chase low side top front orbit.
//                  Without it the game's film-mode director glides between shots every 6.5 s.
//   --warm N       seconds simulated before the first frame (default 6)
//   --out PATH     .mp4 file, or a folder when --png is given (default out/gemini-neon.mp4)
//   --png          keep a PNG sequence instead of encoding an MP4
//   --three DIR    serve three.js from a local copy (node_modules/three) instead of cdn.jsdelivr.net
//   --headed       show the browser window (uses the GPU instead of the software renderer)
//
// Needs: Node 18+, `npm install` in this folder (installs Playwright), `npx playwright install chromium`,
// and ffmpeg on PATH for MP4 output.

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const here = dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 && args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : def; };
const flag = (name) => args.includes('--' + name);

const seconds = parseFloat(opt('seconds', '12'));
const fps = parseInt(opt('fps', '60'), 10);
const seed = parseInt(opt('seed', '20261122'), 10);
const warm = parseFloat(opt('warm', '6'));
const pngOnly = flag('png');
const out = resolve(opt('out', pngOnly ? 'out/frames' : 'out/gemini-neon.mp4'));
const threeDir = opt('three', null);
const shots = (opt('shots', '') || '').split(',').filter(Boolean).map((s) => { const [name, sec] = s.split(':'); return { name: name.trim(), sec: parseFloat(sec) }; });

const page_url = pathToFileURL(join(here, 'index.html')).href;
if (!existsSync(join(here, 'index.html'))) {
  console.error('index.html not found. Run `node build-standalone.mjs` first.');
  process.exit(1);
}
const framesDir = pngOnly ? out : join(dirname(out), '.frames-' + Date.now());
mkdirSync(framesDir, { recursive: true });

const browser = await chromium.launch({
  headless: !flag('headed'),
  args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await (await browser.newContext({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 1 })).newPage();
if (threeDir) {
  await page.route('https://cdn.jsdelivr.net/npm/three@0.170.0/**', (route) => {
    const rel = route.request().url().split('three@0.170.0/')[1];
    route.fulfill({ path: join(resolve(threeDir), rel), contentType: 'text/javascript' });
  });
}
page.on('pageerror', (e) => console.error('[page error]', e.message));
await page.goto(page_url);
await page.waitForFunction(() => window.__gnReady === true, null, { timeout: 180000 });

const size = await page.evaluate((o) => window.__gn.offline(o), { fps, seed, film: shots.length === 0, warm, shot: shots[0]?.name ?? null });
console.log(`rendering ${seconds}s @ ${fps}fps -> ${size.width}x${size.height}`);

const total = Math.round(seconds * fps);
const cuts = [];
let acc = 0;
for (const s of shots) { cuts.push({ frame: Math.round(acc * fps), name: s.name }); acc += s.sec; }
const t0 = Date.now();
for (let f = 0; f < total; f++) {
  const cut = cuts.find((c) => c.frame === f);
  if (cut && f > 0) await page.evaluate((n) => window.__gn.setShot(n, true), cut.name);
  const url = await page.evaluate(() => window.__gn.step(1));
  writeFileSync(join(framesDir, `frame_${String(f + 1).padStart(5, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
  if ((f + 1) % fps === 0 || f + 1 === total) {
    const el = (Date.now() - t0) / 1000, per = el / (f + 1);
    console.log(`  ${f + 1}/${total} frames  ${per.toFixed(2)} s/frame  eta ${Math.round(per * (total - f - 1))} s`);
  }
}
await browser.close();

if (pngOnly) {
  console.log(`PNG sequence written to ${framesDir}`);
} else {
  mkdirSync(dirname(out), { recursive: true });
  const r = spawnSync('ffmpeg', ['-y', '-framerate', String(fps), '-i', join(framesDir, 'frame_%05d.png'),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-r', String(fps), '-movflags', '+faststart',
    extname(out) ? out : out + '.mp4'], { stdio: 'inherit' });
  if (r.status === 0) { rmSync(framesDir, { recursive: true, force: true }); console.log(`MP4 written to ${out}`); }
  else console.error(`ffmpeg failed or is missing; the PNG frames are kept in ${framesDir}`);
}
