#!/usr/bin/env python3
"""RGB + Depth + Alpha video -> cinematic "4D" point-cloud video.

Each frame is unprojected into a 3D point cloud from the depth pass, the alpha
pass separates subject from environment, and a virtual camera flies through the
cloud. On top: depth fog, LiDAR scan pulse, rising embers, transition bursts,
bloom, anamorphic streaks, god rays, ACES tonemap, letterbox, grain.

Usage:
  python render_pointcloud4d.py --rgb RGB.mp4 --depth Depth.mp4 --alpha Alpha.mp4 \
      --out out.mp4 [--frames 0,120,240] [--scale 0.5] [--workers 4]
Depth convention: dark = near, white = far (Depth-Anything style inverted).
"""
import argparse
import os
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np

W, H, FPS = 1920, 1080, 24
SRC_FOV = 55.0
Z_NEAR, Z_FAR = 2.5, 13.0
TARGET = np.array([0.0, 0.25, 7.0], np.float32)  # look-at point in source-cam space (Y down)

# (time s, yaw deg, pitch deg, distance, fov deg, dutch deg)
CAM_KEYS = np.array([
    [0.0, -26, 14, 11.0, 46, -3],
    [2.5, -13, 6, 7.4, 54, -1],
    [5.0, 11, -2, 6.4, 56, 1.5],
    [7.5, 18, 6, 7.8, 50, 2],
    [10.0, 1, 1, 5.2, 60, 0],
    [12.5, -15, -3, 6.8, 55, -2],
    [15.0, -12, 4, 10.0, 38, -1],   # dolly-zoom start
    [17.0, -3, 7, 5.0, 64, 1],      # dolly-zoom end
    [19.96, 20, 20, 12.0, 48, 3],
], np.float32)


def catmull(keys, t):
    ts = keys[:, 0]
    i = int(np.clip(np.searchsorted(ts, t) - 1, 0, len(ts) - 2))
    p0, p1 = keys[max(i - 1, 0), 1:], keys[i, 1:]
    p2, p3 = keys[i + 1, 1:], keys[min(i + 2, len(ts) - 1), 1:]
    u = np.clip((t - ts[i]) / (ts[i + 1] - ts[i]), 0, 1)
    u = u * u * (3 - 2 * u)  # ease in/out per segment
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)


def rot(yaw, pitch, roll):
    y, p, r = np.radians([yaw, pitch, roll])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    Rz = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    return (Ry @ Rx @ Rz).astype(np.float32)


def camera(t, target=TARGET, zscale=1.0):
    yaw, pitch, dist, fov, roll = catmull(CAM_KEYS, t)
    # handheld drift
    yaw += 0.6 * np.sin(t * 1.3) + 0.3 * np.sin(t * 3.1)
    pitch += 0.4 * np.sin(t * 1.7 + 1) + 0.2 * np.sin(t * 4.3)
    R = rot(yaw, -pitch, roll)  # cam->world
    pos = target - R @ np.array([0, 0, dist * zscale], np.float32)
    return R, pos, fov


def srgb2lin(x):
    return np.power(x, 2.2)


def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


class Static:
    """Per-sample stable random attributes (keeps jitter temporally coherent)."""

    def __init__(self, step, seed):
        rng = np.random.default_rng(seed)
        gy, gx = np.mgrid[0:H:step, 0:W:step]
        n = gx.size
        self.u = np.clip(gx.ravel() + rng.random(n) * step, 0, W - 1).astype(np.float32)
        self.v = np.clip(gy.ravel() + rng.random(n) * step, 0, H - 1).astype(np.float32)
        self.ui, self.vi = self.u.astype(np.int32), self.v.astype(np.int32)
        self.r = rng.random(n).astype(np.float32)
        d = rng.normal(size=(n, 3)).astype(np.float32)
        self.dir = d / np.linalg.norm(d, axis=1, keepdims=True)
        self.phase = (rng.random(n) * 6.283).astype(np.float32)


def analyze(rgb_path, depth_path, alpha_path, out_npz):
    """One pass over depth/alpha/audio: transition energy, subject depth, loudness."""
    cd, ca = cv2.VideoCapture(depth_path), cv2.VideoCapture(alpha_path)
    diff, sz, sv, prev = [], [], [], None
    while True:
        okd, fd = cd.read()
        oka, fa = ca.read()
        if not okd:
            break
        g = cv2.resize(fd[:, :, 0], (160, 90)).astype(np.float32)
        a = cv2.resize(fa[:, :, 0], (160, 90)) > 128 if oka else np.zeros((90, 160), bool)
        diff.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
        dn = np.median(g[a]) / 255 if a.sum() > 50 else np.nan
        sz.append(Z_NEAR + (Z_FAR - Z_NEAR) * dn ** 1.8 if dn == dn else np.nan)
        sv.append(np.nonzero(a)[0].mean() / 90 * H if a.sum() > 50 else np.nan)
    def smooth(x, default):
        x = np.array(x, np.float32)
        good = ~np.isnan(x)
        x = np.interp(np.arange(len(x)), np.nonzero(good)[0], x[good]) if good.any() else np.full(len(x), default)
        k = np.hanning(49); k /= k.sum()
        return np.convolve(np.pad(x, 24, mode="edge"), k, "valid")
    sz, sv = smooth(sz, 7.0), smooth(sv, H / 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", rgb_path, "-vn", "-ac", "1", "-ar", "24000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    au = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    m = len(au) // 1000
    rms = np.sqrt((au[:m * 1000].reshape(m, 1000) ** 2).mean(1)) if m else np.zeros(1)
    np.savez(out_npz, diff=np.array(diff, np.float32), subjz=sz.astype(np.float32),
             subjv=sv.astype(np.float32), rms=rms)


def build_energy(d, n):
    d = np.pad(d[:n], (0, max(0, n - len(d))))
    e = np.clip((d - 5) / 40, 0, 1)
    k = np.exp(-np.abs(np.arange(-12, 13)) / 4.0)
    e = np.convolve(e, k, "same")
    return np.clip(e / max(e.max(), 1e-6) * 1.2, 0, 1).astype(np.float32)


def build_audio(r, n):
    r = np.interp(np.linspace(0, len(r) - 1, n), np.arange(len(r)), r)
    r = np.convolve(r, np.ones(3) / 3, "same")
    return np.clip(r / (np.percentile(r, 98) + 1e-6), 0, 1.3).astype(np.float32)


def render_frame(fi, rgb, depth, alpha, ctx, scale=1.0):
    ow, oh = int(W * scale), int(H * scale)
    t = fi / FPS
    T = ctx["duration"]
    energy = float(ctx["energy"][min(fi, len(ctx["energy"]) - 1)])
    aud = float(ctx["audio"][min(fi, len(ctx["audio"]) - 1)])

    dep = cv2.medianBlur(depth, 5).astype(np.float32) / 255.0
    dep = cv2.GaussianBlur(dep, (0, 0), 1.6)
    alp = cv2.GaussianBlur(alpha, (5, 5), 0).astype(np.float32) / 255.0
    gx = cv2.Sobel(dep, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(dep, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    edge = cv2.morphologyEx(alpha, cv2.MORPH_GRADIENT, np.ones((7, 7), np.uint8)).astype(np.float32) / 255.0
    col = srgb2lin(rgb[:, :, ::-1].astype(np.float32) / 255.0)

    S1, S2 = ctx["bg"], ctx["fg"]
    a2 = alp[S2.vi, S2.ui]
    keep2 = a2 > 0.5
    parts = []
    for S, mask in ((S1, None), (S2, keep2)):
        idx = np.nonzero(mask)[0] if mask is not None else slice(None)
        u, v, ui, vi = S.u[idx], S.v[idx], S.ui[idx], S.vi[idx]
        parts.append(dict(u=u, v=v, d=dep[vi, ui], a=alp[vi, ui], g=grad[vi, ui],
                          e=edge[vi, ui], c=col[vi, ui], r=S.r[idx], dir=S.dir[idx], ph=S.phase[idx]))
    P = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

    # drop flying pixels on depth discontinuities (keep a few as streak dust)
    ok = (P["g"] < 0.35) | (P["r"] < 0.08)
    P = {k: v[ok] for k, v in P.items()}

    d = np.clip(P["d"] + (P["r"] - 0.5) * (1.5 / 255), 0, 1)  # dither 8-bit depth steps
    Z = Z_NEAR + (Z_FAR - Z_NEAR) * np.power(d, 1.8)
    sky = d > 0.965
    Z = np.where(sky, Z_FAR + 6 * P["r"], Z)
    f0 = (W / 2) / np.tan(np.radians(SRC_FOV / 2))
    X = (P["u"] - W / 2) / f0 * Z
    Y = (P["v"] - H / 2) / f0 * Z
    pts = np.stack([X, Y, Z], 1).astype(np.float32)
    subj = P["a"] > 0.5

    # ---- 4D motion -------------------------------------------------------
    j = min(fi, len(ctx["subjz"]) - 1)
    tz = float(ctx["subjz"][j])
    tgt = np.array([0.0, (float(ctx["subjv"][j]) - H / 2) / f0 * tz, tz], np.float32)
    # transition burst: vortex around the subjects' axis + lift + scatter, then reassemble
    burst = energy * (0.4 + 1.6 * P["r"] ** 2)
    ang = energy * (0.6 + 2.4 * P["r"] ** 1.5) * (1.0 + 0.5 * np.sin(P["ph"]))
    rx, rz = pts[:, 0] - tgt[0], pts[:, 2] - tgt[2]
    ca_, sa_ = np.cos(ang), np.sin(ang)
    pts[:, 0] = tgt[0] + rx * ca_ - rz * sa_
    pts[:, 2] = tgt[2] + rx * sa_ + rz * ca_
    pts[:, 1] -= burst * 0.8 * P["r"]
    pts += P["dir"] * (burst * 0.25)[:, None]
    # intro assembly / outro dispersion
    intro = np.clip(1 - t / 2.2, 0, 1) ** 2
    outro = np.clip((t - (T - 2.0)) / 2.0, 0, 1) ** 1.5
    if intro > 0:
        delay = np.clip(intro * 1.6 - P["r"] * 0.6, 0, 1)
        pts += P["dir"] * (delay * 9)[:, None]
    if outro > 0:
        o = np.clip(outro * 1.8 - P["r"] * 0.8, 0, 1)
        ang = o * o * (1.5 + 2 * P["r"])
        rx, rz = pts[:, 0] - tgt[0], pts[:, 2] - tgt[2]
        pts[:, 0] = tgt[0] + rx * np.cos(ang) - rz * np.sin(ang)
        pts[:, 2] = tgt[2] + rx * np.sin(ang) + rz * np.cos(ang)
        pts[:, 1] -= o * o * 4 * (0.3 + P["r"])
        pts += P["dir"] * (o * 1.2)[:, None]
    # drifting shimmer on environment
    wob = 0.03 * (~subj)
    pts[:, 0] += wob * np.sin(t * 1.7 + P["ph"])
    pts[:, 1] += wob * np.cos(t * 1.3 + P["ph"] * 1.3)
    # rising embers off the subject silhouette
    ember = subj & (P["r"] < 0.004 + 0.035 * P["e"])
    life = (t * 0.35 + P["ph"] / 6.283) % 1.0
    em_rise = np.where(ember, life * 2.2, 0)
    pts[:, 1] -= em_rise
    pts[:, 0] += np.where(ember, 0.25 * np.sin(life * 9 + P["ph"]) * life, 0)

    # ---- shading ---------------------------------------------------------
    c = P["c"].copy()
    lum = c @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # environment: cool teal grade, subject: warm, rich
    env_tint = np.array([0.55, 0.85, 1.15], np.float32)
    c = np.where(subj[:, None], c * np.array([1.12, 1.0, 0.92], np.float32) * 1.4,
                 (0.5 * c + 0.5 * lum[:, None]) * env_tint * 0.8)
    # rim light on subject silhouette (cyan/orange split by screen side)
    rim = P["e"] * subj
    rimcol = np.where((P["u"] < W / 2)[:, None], np.array([0.2, 0.8, 1.6], np.float32),
                      np.array([1.6, 0.6, 0.15], np.float32))
    c += rim[:, None] * rimcol * (0.6 + 0.6 * aud)
    # LiDAR scan pulse travelling through depth
    period = 3.2
    ph = (t % period) / period
    scanZ = Z_NEAR + ph * (Z_FAR + 4 - Z_NEAR)
    band = np.exp(-((Z - scanZ) / 0.35) ** 2) * (1 - ph) ** 0.5
    trail = np.clip(1 - (scanZ - Z) / 3.0, 0, 1) * (Z < scanZ) * 0.25
    c += (band * 3.5 + trail)[:, None] * np.array([0.25, 0.75, 1.3], np.float32)
    # embers: hot emissive
    lifef = np.sin(np.clip(life, 0, 1) * np.pi)
    c = np.where(ember[:, None], np.array([2.4, 1.0, 0.3], np.float32) * (lifef * 1.5 + 0.2)[:, None], c)
    # burst energy tint
    c += (energy * burst * 0.35)[:, None] * np.array([0.4, 0.7, 1.5], np.float32)
    # sparkles: a sparse set of points flare up while the cloud is in motion
    spark = np.maximum(energy, outro) * (P["r"] > 0.93) * (0.5 + 0.5 * np.sin(t * 9 + P["ph"] * 3))
    c += (spark * 4.0)[:, None] * np.array([0.7, 0.9, 1.4], np.float32)
    c *= (1 - intro * 0.6) * (1 - outro * 0.7)

    # ---- project ---------------------------------------------------------
    R, pos, fov = camera(t, tgt, tz / TARGET[2])
    pc = (pts - pos) @ R  # world->cam (R orthonormal)
    zc = pc[:, 2]
    fz = (ow / 2) / np.tan(np.radians(fov / 2))
    front = zc > 0.3
    pc, zc, c, Zs, subj_f, P_r = pc[front], zc[front], c[front], Z[front], subj[front], P["r"][front]
    sx = pc[:, 0] / zc * fz + ow / 2
    sy = pc[:, 1] / zc * fz + oh / 2
    # atmospheric fog
    fog = 1 - np.exp(-np.maximum(zc - 3.0, 0) * 0.075)
    fogcol = np.array([0.012, 0.03, 0.06], np.float32)
    c = c * (1 - fog)[:, None] + fogcol * fog[:, None]
    # point size by distance (near points splat 2x2)
    big = (zc < 5.5 * (0.5 + P_r)) | (subj_f & (zc < 9))
    hw = np.where(subj_f, 0.3, 1.0).astype(np.float32)
    xs, ys, cs, zs, hs = [sx], [sy], [c], [zc], [hw]
    for dx, dy in ((1, 0), (0, 1), (1, 1)):
        xs.append(sx[big] + dx); ys.append(sy[big] + dy); cs.append(c[big]); zs.append(zc[big]); hs.append(hw[big] * 0)
    sx, sy, c, zc, hw = map(np.concatenate, (xs, ys, cs, zs, hs))
    xi, yi = sx.astype(np.int32), sy.astype(np.int32)
    inb = (xi >= 0) & (xi < ow) & (yi >= 0) & (yi < oh)
    xi, yi, c, zc, hw = xi[inb], yi[inb], c[inb], zc[inb], hw[inb]
    pix = yi * ow + xi

    # z-buffered solid layer (far -> near, last write wins)
    order = np.argsort(-zc, kind="stable")
    img = np.zeros((oh * ow, 3), np.float32)
    img[pix[order]] = c[order]
    img = img.reshape(oh, ow, 3)
    # additive luminous haze layer
    acc = np.stack([np.bincount(pix, weights=c[:, k] * hw, minlength=oh * ow) for k in range(3)], 1)
    acc = acc.reshape(oh, ow, 3).astype(np.float32)

    # ---- post ------------------------------------------------------------
    s = scale
    haze = cv2.GaussianBlur(acc, (0, 0), 3 * s) * 0.9 + cv2.GaussianBlur(acc, (0, 0), 14 * s) * 0.5
    out = img + haze * 0.35 * (1 - 0.55 * max(energy, outro))
    # volumetric backlight behind subjects
    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    lx, ly = ow * (0.5 + 0.08 * np.sin(t * 0.4)), oh * 0.30
    rr = np.sqrt(((xx - lx) / ow) ** 2 + ((yy - ly) / oh * 0.8) ** 2)
    out += (np.exp(-rr * 5.0) * 0.10 * (1 + 0.5 * aud))[:, :, None] * np.array([0.35, 0.55, 1.0], np.float32)
    # god rays: radial zoom-blur of bright content from light position
    bright = np.clip(out - 0.6, 0, None)
    small = cv2.resize(bright, (ow // 4, oh // 4), interpolation=cv2.INTER_AREA)
    rays = np.zeros_like(small)
    cx, cy = lx / 4, ly / 4
    for i in range(12):
        k = 1 + i * 0.035
        M = np.float32([[k, 0, cx * (1 - k)], [0, k, cy * (1 - k)]])
        rays += cv2.warpAffine(small, M, (small.shape[1], small.shape[0])) * (1 - i / 12)
    out += cv2.resize(rays, (ow, oh)) * 0.07
    # bloom pyramid
    bsrc = np.clip(out - 0.8, 0, None)
    bloom = np.zeros_like(out)
    for sig, wgt in ((4, 0.5), (12, 0.35), (32, 0.3), (70, 0.2)):
        bloom += cv2.GaussianBlur(bsrc, (0, 0), sig * s) * wgt
    out += bloom * (1 + 0.6 * aud + 0.4 * energy)
    # anamorphic streak
    st = cv2.resize(np.clip(out - 1.4, 0, None), (ow // 4, oh // 4), interpolation=cv2.INTER_AREA)
    st = cv2.blur(st, (int(151 * s) | 1, 1))
    st = cv2.blur(st, (int(151 * s) | 1, 1))
    out += cv2.resize(st, (ow, oh))[:, :, :] * np.array([0.3, 0.6, 1.4], np.float32) * 0.9
    # exposure + transition flash
    out *= 1.5 + 0.3 * energy ** 2
    # ACES tonemap -> display
    out = aces(out)
    out = np.power(out, 1 / 2.2)
    # chromatic aberration (radial)
    ca = 1.0015 + 0.004 * energy
    M_r = np.float32([[ca, 0, ow / 2 * (1 - ca)], [0, ca, oh / 2 * (1 - ca)]])
    M_b = np.float32([[1 / ca, 0, ow / 2 * (1 - 1 / ca)], [0, 1 / ca, oh / 2 * (1 - 1 / ca)]])
    out[:, :, 0] = cv2.warpAffine(out[:, :, 0], M_r, (ow, oh), borderMode=cv2.BORDER_REFLECT)
    out[:, :, 2] = cv2.warpAffine(out[:, :, 2], M_b, (ow, oh), borderMode=cv2.BORDER_REFLECT)
    # vignette
    vig = 1 - 0.55 * np.clip(((xx / ow - 0.5) ** 2 + (yy / oh - 0.5) ** 2) * 2.2, 0, 1) ** 1.5
    out *= vig[:, :, None]
    # grain
    rng = np.random.default_rng(fi)
    out += (rng.standard_normal((oh, ow, 1)).astype(np.float32) * 0.018)
    # letterbox 2.39:1 with a soft open at the intro
    bar = int(round((oh - ow / 2.39) / 2 * min(1, t / 1.2 + 0.4)))
    if bar > 0:
        out[:bar] = 0
        out[oh - bar:] = 0
    out = np.clip(out * 255, 0, 255).astype(np.uint8)[:, :, ::-1]  # -> BGR
    return out


def make_ctx(n, npz):
    A = np.load(npz)
    pad = lambda x: np.pad(x[:n], (0, max(0, n - len(x))), mode="edge")
    return dict(bg=Static(2, 1), fg=Static(1, 2), duration=n / FPS,
                energy=build_energy(A["diff"], n), audio=build_audio(A["rms"], n),
                subjz=pad(A["subjz"]), subjv=pad(A["subjv"]))


def read_frame(cap, i):
    ok, f = cap.read()
    return f if ok else None


def worker(job):
    args, start, end, tmp = job
    n = args.n
    ctx = make_ctx(n, args.analysis)
    caps = [cv2.VideoCapture(p) for p in (args.rgb, args.depth, args.alpha)]
    for c in caps:
        for _ in range(start):
            c.grab()
    ow, oh = int(W * args.scale), int(H * args.scale)
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"MJPG"), FPS, (ow, oh))
    last = [None, None, None]
    for fi in range(start, end):
        fr = []
        for k, c in enumerate(caps):
            f = read_frame(c, fi)
            last[k] = f if f is not None else last[k]
            fr.append(last[k])
        rgb, dep, alp = fr[0], fr[1][:, :, 0], fr[2][:, :, 0]
        vw.write(render_frame(fi, rgb, dep, alp, ctx, args.scale))
        if (fi - start) % 10 == 0:
            print(f"[{start}-{end}] frame {fi}", flush=True)
    vw.release()
    return tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rgb", required=True)
    ap.add_argument("--depth", required=True)
    ap.add_argument("--alpha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()
    args.n = int(cv2.VideoCapture(args.rgb).get(cv2.CAP_PROP_FRAME_COUNT))
    args.analysis = os.path.splitext(args.out)[0] + "_analysis.npz"
    if not os.path.exists(args.analysis):
        analyze(args.rgb, args.depth, args.alpha, args.analysis)

    if args.frames:  # preview stills
        ctx = make_ctx(args.n, args.analysis)
        caps = [cv2.VideoCapture(p) for p in (args.rgb, args.depth, args.alpha)]
        for fi in map(int, args.frames.split(",")):
            fr = []
            for c in caps:
                c.set(cv2.CAP_PROP_POS_FRAMES, fi)
                fr.append(c.read()[1])
            img = render_frame(fi, fr[0], fr[1][:, :, 0], fr[2][:, :, 0], ctx, args.scale)
            cv2.imwrite(f"{args.out}_{fi:04d}.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return

    tmpdir = os.path.splitext(args.out)[0] + "_parts"
    os.makedirs(tmpdir, exist_ok=True)
    bounds = np.linspace(0, args.n, args.workers + 1).astype(int)
    jobs = [(args, bounds[i], bounds[i + 1], os.path.join(tmpdir, f"part{i:02d}.avi"))
            for i in range(args.workers)]
    with Pool(args.workers) as p:
        parts = p.map(worker, jobs)
    lst = os.path.join(tmpdir, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{os.path.abspath(x)}'\n" for x in parts)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-i", args.rgb, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-shortest", args.out], check=True)
    print("wrote", args.out)


if __name__ == "__main__":
    sys.exit(main())
