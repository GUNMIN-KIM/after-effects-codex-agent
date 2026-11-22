# Interstellar-style VFX composite over the beach plate. 10 s @ 30 fps, 1080x1920.
#   python comp.py <first> <last> [--preview]       renders output frames first..last (0-based) to work/out/
# Every time-dependent element is a closed-form function of the output frame, so ranges render in parallel.
import os, sys, json, math, glob
os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR', '1')
import numpy as np, cv2
from functools import lru_cache
SP = os.path.dirname(os.path.abspath(__file__))
WK = os.path.join(SP, 'work')
sys.path.insert(0, SP)
from bh_shade import BlackHole, fbm_tex

W, H, NF, FPS = 1080, 1920, 300, 30
F = 1407.0; CX = 540.0; CAM_H = 1.28
MG = 120; CW, CH = W + 2 * MG, H + 2 * MG
SKY_X0, SKY_Y0, SKY_W, SKY_H = -300, -1400, 1680, 2400
Y_PERSON, Y_DOG = 2.39, 2.47
DOG_BOX = (130, 1380, 445, 1725)

trk = json.load(open(os.path.join(WK, 'track.json')))
MS = np.array(trk['M']); k0, c0 = trk['horizon'][0]
RHO = math.atan(k0); VH0 = k0 * CX + c0

def sm(a, b, x):
    t = np.clip((np.asarray(x, np.float32) - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def smf(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0); return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t
def T(x, y): return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], np.float64)
def Rz(a): c, s = math.cos(a), math.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)
A1 = T(CX, VH0) @ Rz(RHO) @ T(-CX, -VH0) @ T(-MG, -MG)          # L-canvas -> frame-1

# ------------------------------------------------------------------ timeline
def src_time(k):
    if k < 60: return float(k)
    if k < 180: return 59.0 + (k - 60) * 62.0 / 120.0
    u = (k - 180) * 0.33; p = u % 26.0
    return 121.0 - (p if p <= 13 else 26 - p)

def M_at(s):
    i = int(math.floor(s)); f = s - i; i = min(i, 120)
    return MS[i] * (1 - f) + MS[min(i + 1, 121)] * f

def push(k):
    z = 1 + 0.05 * smf(180, 300, k); return T(CX, 980) @ np.diag([z, z, 1]) @ T(-CX, -980)

def shake(k):
    a = 0.0
    a += 9 * math.exp(-((k - 152) / 6.0) ** 2)          # sonic boom
    a += 12 * math.exp(-((k - 190) / 7.0) ** 2)         # surge impact
    a += 3 * smf(100, 125, k) * (1 - smf(150, 170, k))  # inside the storm
    return T(a * math.sin(k * 2.7) + 0.4 * a * math.sin(k * 7.3), a * math.cos(k * 3.1))

def storm_D(k):        # dust-wall distance (m); negative = camera inside / behind
    xs = [14, 45, 72, 90, 104, 112, 118, 124]; ys = [7000, 2200, 700, 220, 24, 2.4, 0.0, -6]
    if k < xs[0]: return 1e9
    return float(np.interp(k, xs, ys)) if k <= xs[-1] else -6 - (k - 124) * 0.5
def dust_inside(k): return smf(108, 124, k) * (1 - 0.82 * smf(138, 170, k)) * (1 - 0.6 * smf(200, 260, k))
def space_amt(k): return smf(122, 150, k)
def storm_amt(k): return (0.3 * smf(36, 90, k) + 0.7 * smf(92, 116, k)) * (1 - 0.7 * smf(140, 175, k))
def front_F(k): return 6.1 if k < 168 else max(0.0, 6.1 * (1 - smf(168, 198, k) ** 0.9))
def level_h(k): return 0.45 * smf(172, 205, k) + 0.4 * smf(205, 246, k)
def sink_p(k): return 1.5 * smf(244, 272, k) ** 1.4
SHIP_K0 = 136

# ------------------------------------------------------------------ assets (cached)
def to_lin(img8): return (img8.astype(np.float32) / 255.0) ** 2.2

@lru_cache(maxsize=6)
def plate(i):
    return to_lin(cv2.imread(os.path.join(SP, 'plate', 'p_%04d.png' % (i + 1)))[..., ::-1].copy())
@lru_cache(maxsize=6)
def alpha(i):
    p = os.path.join(WK, 'alpha', 'a_%04d.png' % (i + 1))
    a = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    return (a.astype(np.float32) / 255.0) if a is not None else np.zeros((H, W), np.float32)
_dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
@lru_cache(maxsize=6)
def flow(i, j):
    a = cv2.cvtColor(cv2.imread(os.path.join(SP, 'plate', 'p_%04d.png' % (i + 1))), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cv2.imread(os.path.join(SP, 'plate', 'p_%04d.png' % (j + 1))), cv2.COLOR_BGR2GRAY)
    a, b = cv2.resize(a, (W // 2, H // 2)), cv2.resize(b, (W // 2, H // 2))
    fl = _dis.calc(a, b, None)
    return cv2.resize(fl, (W, H)) * 2.0
GX, GY = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
def interp_src(s):
    i = int(math.floor(s)); f = s - i
    if f < 0.02 or i >= 121: i = min(int(round(s)), 121); return plate(i), alpha(i)
    f01, f10 = flow(i, i + 1), flow(i + 1, i)
    m0x, m0y = GX - f * f01[..., 0], GY - f * f01[..., 1]
    m1x, m1y = GX - (1 - f) * f10[..., 0], GY - (1 - f) * f10[..., 1]
    p = cv2.remap(plate(i), m0x, m0y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) * (1 - f) + cv2.remap(plate(i + 1), m1x, m1y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) * f
    a = cv2.remap(alpha(i), m0x, m0y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) * (1 - f) + cv2.remap(alpha(i + 1), m1x, m1y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) * f
    return p, a

_bh = None
def bh():
    global _bh
    if _bh is None:
        maps = os.path.join(WK, 'bh_maps_1680x3660.npz')
        _bh = BlackHole(maps)
        for name in ('hit', 'r', 'phi', 'side', 'hit2', 'r2', 'phi2', 'esc', 'cap', 'mapx', 'mapy', 'stars'):
            setattr(_bh, name, getattr(_bh, name)[:SKY_H].copy())   # only the rows the sky canvas uses
    return _bh
_noise = {}
def noise(name, h, w, octv, seed):
    if name not in _noise:
        p = os.path.join(WK, 'noise_%s.npy' % name)
        if os.path.exists(p): _noise[name] = np.load(p)
        else: _noise[name] = fbm_tex(h, w, octv, seed); np.save(p, _noise[name])
    return _noise[name]

# L-canvas coordinate grids
LU, LV = np.meshgrid(np.arange(CW, dtype=np.float32) - MG, np.arange(CH, dtype=np.float32) - MG)
above = LV < VH0
tanE = np.clip((VH0 - LV) / F, 0, None)
Yg = np.where(LV > VH0 + 0.5, CAM_H * F / np.maximum(LV - VH0, 0.5), 1e6).astype(np.float32)

# ------------------------------------------------------------------ sky (space) canvas, in L coords offset by SKY_X0/Y0
def space_sky(k):
    img = bh().render(k / FPS * 1.4, disk_gain=1.0, star_gain=1.5)        # cropped to the 2400 canvas rows
    tw = 1 - 0.25 * math.sin(k * 0.13)
    return (img * np.float32(1.15)).astype(np.float32)

def sky_to_L(sky):
    # canvas pixel (x, y) in L coords = (x + SKY_X0, y + SKY_Y0); L-canvas pixel = L + MG
    M = np.float32([[1, 0, -SKY_X0 - MG], [0, 1, -SKY_Y0 - MG]])
    return cv2.warpAffine(sky, M, (CW, CH), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)

# ------------------------------------------------------------------ dust
DUST_LIGHT = np.array([0.40, 0.29, 0.18], np.float32)
DUST_DARK = np.array([0.07, 0.05, 0.03], np.float32)

# ---- Cycles volumetric dust wall (rendered every 2nd frame, k 14..118) ----
@lru_cache(maxsize=4)
def dust_npy(k):
    p = os.path.join(WK, 'dust', 'd_%04d.npy' % k)
    if not os.path.exists(p): return None
    d = np.load(p).astype(np.float32)
    d = cv2.resize(d, (W, H), interpolation=cv2.INTER_CUBIC)
    d[..., 3] = np.clip(d[..., 3], 0, 1); d[..., :3] = np.clip(d[..., :3], 0, None)
    return d
def dust_frames():
    return sorted(int(os.path.basename(p)[2:6]) for p in glob.glob(os.path.join(WK, 'dust', 'd_*.npy')))
def dust_vol(k):
    if k < 14 or k > 118: return None
    fr = dust_frames()
    if not fr: return None
    lo = [r for r in fr if r <= k]; hi = [r for r in fr if r >= k]
    if not lo: return dust_npy(hi[0])
    if not hi: return dust_npy(lo[-1])
    a_k, b_k = lo[-1], hi[0]
    if a_k == b_k: return dust_npy(a_k)
    f = (k - a_k) / (b_k - a_k)
    a, b = dust_npy(a_k), dust_npy(b_k)
    g = lambda d: np.clip((d[..., 3] * 0.6 + d[..., :3].mean(-1)) * 200, 0, 255).astype(np.uint8)
    ga, gb = cv2.resize(g(a), (W // 2, H // 2)), cv2.resize(g(b), (W // 2, H // 2))
    fab = cv2.resize(_dis.calc(ga, gb, None), (W, H)) * 2.0; fba = cv2.resize(_dis.calc(gb, ga, None), (W, H)) * 2.0
    wa = cv2.remap(a, GX - f * fab[..., 0], GY - f * fab[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    wb = cv2.remap(b, GX - (1 - f) * fba[..., 0], GY - (1 - f) * fba[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return (1 - f) * wa + f * wb
def dust_layer(k):
    """Returns (rgb, alpha_back, veil) on the L canvas. alpha_back covers what is behind the person."""
    D = storm_D(k)
    n1 = noise('d1', 1024, 1024, 8, 21); n2 = noise('d2', 1024, 1024, 7, 22); n3 = noise('d3', 512, 2048, 7, 23)
    zoom = float(np.clip(900.0 / max(D, 1.0), 0.6, 5.0)) if D > 0 else 5.0
    sx = (LU - CX) / (zoom * 2.2) + 512 - k * 2.4 / zoom
    sy = (LV - VH0) / (zoom * 2.2) + 512 + k * 1.1 / zoom
    warp = cv2.remap(n2, (sx * 0.7) % 1024, (sy * 0.7) % 1024, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) - 0.5
    mx, my = (sx + warp * 90) % 1024, (sy + warp * 60) % 1024
    T1 = cv2.remap(n1, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    T1b = cv2.remap(n1, (mx + 2.0) % 1024, (my + 3.5) % 1024, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    lit = np.clip((T1 - T1b) * 14 + 0.5, 0, 1)          # fine billow highlights (light from upper left)
    bx, by = (sx * 0.45 + warp * 40) % 1024, (sy * 0.45 + warp * 30) % 1024
    B1 = cv2.remap(n1, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    B2 = cv2.remap(n1, (bx + 9) % 1024, (by + 16) % 1024, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    broad = np.clip((B1 - B2) * 9 + 0.5, 0, 1)         # large cauliflower lobes: lit tops, shadowed undersides
    T1 = np.clip((T1 - 0.5) * 1.6 + 0.5, 0, 1)
    edge_noise = cv2.remap(n3, ((LU * 0.35 - k * 1.2) % 2048), (LV * 0 + 200).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    cov = np.zeros((CH, CW), np.float32)
    if D > 0:
        top = 320.0 / max(D, 1e-3) * (0.6 + 0.8 * edge_noise)
        cov_sky = sm(top * 1.08, top * 0.8, tanE)
        cov_gnd = sm(D * (0.75 + 0.5 * edge_noise) - 1.5, D * (0.75 + 0.5 * edge_noise) + 4.0 + 0.2 * D, Yg)
        skirt = sm(D * 0.12, D * 0.9, Yg) * 0.55 * smf(20, 70, k)          # sand blown ahead of the wall
        cov = np.where(above, 0.0, skirt * (0.45 + 0.6 * edge_noise) * sm(0.2, 0.6, T1)).astype(np.float32)
        # dense dust hugging the ground at the wall's foot: blends the volume's base into the horizon
        hgt_m = tanE * D
        foot = np.exp(-hgt_m / (32.0 + 50.0 * edge_noise)) * (0.75 + 0.35 * T1) * float(np.clip(1.45 - D / 12000.0, 0, 1))
        cov = np.where(above, np.clip(foot, 0, 0.92), cov).astype(np.float32)
    inside = dust_inside(k)
    if inside > 0:
        clear = sm(0.0, 1.0, (k - 130) / 24.0 + tanE * 1.3 - 0.25) if k > 128 else np.zeros_like(tanE)
        fog = inside * (0.7 + 0.5 * T1) * (1 - np.where(above, clear, 0.6 * clear))
        cov = np.maximum(cov, np.clip(fog, 0, 1))
    hgt = np.clip(tanE * max(D, 1.0) / 320.0, 0, 1.2) if D > 0 else np.clip(tanE, 0, 1)
    shade = np.clip(0.08 + 0.62 * broad ** 1.3 + 0.22 * lit + 0.18 * T1 + 0.22 * hgt, 0, 1.3)
    far = float(np.clip((D - 300) / 6000, 0, 1)) if D > 0 else 0.0
    sp = space_amt(k)
    light = lerp(1.0, 0.55, storm_amt(k)) * lerp(1.0, 0.45, sp)
    col = (DUST_DARK + (DUST_LIGHT - DUST_DARK) * shade[..., None]) * light
    col = col * (1 - 0.45 * far) + np.array([0.42, 0.40, 0.40], np.float32) * 0.55 * far * light
    col = col * lerp(np.ones(3, np.float32), np.array([1.15, 0.85, 0.6], np.float32), sp)
    veil_amt = 0.0
    if D < Y_PERSON and k > 118: veil_amt = 0.4 * (1 - 0.85 * smf(130, 165, k))
    veil = np.clip(veil_amt * (0.5 + 0.8 * T1) * (0.6 + 0.6 * (LV > VH0)), 0, 0.85)
    return col.astype(np.float32), cov.astype(np.float32), veil.astype(np.float32)

# ------------------------------------------------------------------ water (ray-traced plane + Gerstner-ish wave sum)
rng_w = np.random.default_rng(5)
WAVES = []
for i in range(20):
    lam = float(np.exp(rng_w.uniform(np.log(0.35), np.log(22.0))))
    ang = math.radians(270 + rng_w.normal(0, 35 if lam > 3 else 80))
    A = 0.018 * lam ** 0.85 * rng_w.uniform(0.6, 1.2)
    WAVES.append((lam, math.cos(ang), math.sin(ang), A, rng_w.uniform(0, 6.28)))
RIPPLES = []
for i in range(28):
    lam = float(np.exp(rng_w.uniform(np.log(0.08), np.log(1.2))))
    ang = rng_w.uniform(0, 2 * math.pi)
    RIPPLES.append((lam, math.cos(ang), math.sin(ang), rng_w.uniform(0.05, 0.11), rng_w.uniform(0, 6.28)))
def water_layer(k, sky_canvas):
    h = level_h(k); Fk = front_F(k)
    y0 = int(math.ceil(VH0 + MG + 1.0))
    v = LV[y0:]; u = LU[y0:]
    dyv = (v - VH0) / F; dxv = (u - CX) / F
    t = (CAM_H - h) / np.maximum(dyv, 1e-4)
    X = t * dxv; Y = t
    foot = t / F
    tt = k / FPS
    gx = np.zeros_like(t); gy = np.zeros_like(t); eta = np.zeros_like(t)
    calm = lerp(1.0, 0.75, smf(250, 290, k))
    for lam, cx_, cy_, A, ph in WAVES:
        kk = 2 * math.pi / lam; om = math.sqrt(9.81 * kk)
        w = np.clip(lam / (6 * foot) - 1, 0, 1)
        if not w.any(): continue
        arg = kk * (cx_ * X + cy_ * Y) - om * tt + ph
        A2 = A * calm
        eta += A2 * np.sin(arg) * w
        c = A2 * kk * np.cos(arg) * w
        gx += c * cx_; gy += c * cy_
    # the surge: a long swell rolling toward the camera
    sA = 0.32 * smf(160, 178, k) * (1 - smf(205, 240, k))
    if sA > 0:
        lam = 16.0; kk = 2 * math.pi / lam; om = math.sqrt(9.81 * kk) * 1.6
        arg = kk * (-Y) - om * tt
        w = np.clip(lam / (6 * foot) - 1, 0, 1)
        eta += sA * np.sin(arg) * w; gy += -sA * kk * np.cos(arg) * w
    # small ripples: many short directional sine waves, filtered by pixel footprint -> broken glitter path
    for lam, cx_, cy_, slope, ph in RIPPLES:
        w = np.clip(lam / (4 * foot) - 1, 0, 1)
        if not w.any(): continue
        kk = 2 * math.pi / lam; om = math.sqrt(9.81 * kk + 0.074 / 1000 * kk ** 3)
        c = slope * calm * np.cos(kk * (cx_ * X + cy_ * Y) - om * tt + ph) * w
        gx += c * cx_; gy += c * cy_
    n = np.stack([-gx, -gy, np.ones_like(gx)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    d = np.stack([dxv, np.ones_like(dxv), -dyv], -1); d /= np.linalg.norm(d, axis=-1, keepdims=True)
    cosi = np.clip(-(d * n).sum(-1), 0, 1)
    r = d + 2 * cosi[..., None] * n
    rz = np.maximum(r[..., 2], 0.004); ry = np.maximum(r[..., 1], 0.05)
    ur = CX + F * r[..., 0] / ry - SKY_X0; vr = VH0 - F * rz / ry - SKY_Y0
    refl = cv2.remap(sky_canvas, ur.astype(np.float32), vr.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    fres = 0.02 + 0.98 * (1 - cosi) ** 5
    amb = lerp(1.0, 0.25, space_amt(k))
    body = np.array([0.004, 0.016, 0.02], np.float32) * amb + np.array([0.02, 0.09, 0.08], np.float32)[None, None] * np.clip(eta * 3, 0, 1)[..., None] * amb
    col = refl * fres[..., None] + body * (1 - fres[..., None])
    # foam: churning front + crest foam during the surge
    fn = noise('foam', 1024, 1024, 6, 31)
    fx = (X * 38 + 512) % 1024; fy = (Y * 38 + k * 3) % 1024
    fv = cv2.remap(fn, fx.astype(np.float32), fy.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    front = np.exp(-((Y - Fk) / (0.35 + 0.08 * Y)) ** 2) * (Fk > 0.05) * (Fk < 6.0)
    crest = np.clip((eta - 0.24) * 5, 0, 1) * smf(165, 185, k) * (1 - smf(212, 240, k))
    streak = np.clip((fv - 0.42) * 4.0, 0, 1)
    foam = np.clip((front * 1.2 + crest * 0.8) * streak * (0.5 + 0.8 * fv), 0, 0.95) * np.clip(1.6 - foot * 40, 0, 1)
    foam_col = np.array([0.75, 0.8, 0.82], np.float32) * lerp(1.0, 0.35, space_amt(k)) + np.array([0.12, 0.08, 0.04], np.float32) * space_amt(k)
    col = col * (1 - foam[..., None]) + foam_col * foam[..., None]
    a = sm(Fk - 0.1, Fk + 0.35 + 0.25 * fv, Y) if Fk > 0 else np.ones_like(Y)
    out = np.zeros((CH, CW, 3), np.float32); al = np.zeros((CH, CW), np.float32)
    out[y0:] = col; al[y0:] = a
    return out, al

# ------------------------------------------------------------------ particles (closed form, deterministic)
rng_p = np.random.default_rng(9)
NP = 2600
P0 = np.stack([rng_p.uniform(-14, 14, NP), np.exp(rng_p.uniform(np.log(1.3), np.log(30), NP)), rng_p.uniform(0, 1, NP) ** 2.6 * 2.6], 1)
PV = rng_p.uniform(0.6, 1.4, NP); PPH = rng_p.uniform(0, 6.28, NP); PSZ = rng_p.uniform(0.6, 1.8, NP)
def particles(k, Gk):
    """Wind-blown sand grains as motion-blurred streaks. Returns back/front premultiplied layers (frame space)."""
    amt = smf(25, 70, k) * (1 - 0.85 * smf(122, 150, k)) * (1 - smf(185, 210, k))
    back = np.zeros((H, W), np.uint8); front = np.zeros((H, W), np.uint8)
    if amt <= 0.01: return back, front, amt
    tt = k / FPS; wind = 16.0 * (0.4 + 0.6 * smf(40, 110, k))
    n_use = int(NP * min(1.0, 0.15 + amt))
    x = ((P0[:, 0] - wind * PV * tt + 14) % 28) - 14
    y = P0[:, 1] + 0.3 * np.sin(tt * 1.3 + PPH)
    z = np.clip(P0[:, 2] * np.clip(P0[:, 1] / 6.0, 0.25, 1.0) + 0.25 * np.sin(tt * 3.1 + PPH * 2) + 0.15 * np.sin(tt * 7 + PPH), 0.02, 4)
    dz = 0.12 * np.cos(tt * 3.1 + PPH * 2)
    dx = -wind * PV / FPS * 0.3
    def proj(X, Y, Z):
        u = CX + F * X / Y; v = VH0 + F * (CAM_H - Z) / Y
        p = Gk @ np.vstack([u + MG, v + MG, np.ones_like(u)]); return p[0], p[1]
    u1, v1 = proj(x, y, z); u0, v0 = proj(x - dx, y, z - dz)
    for i in range(n_use):
        if y[i] < 0.5: continue
        thick = max(1, int(PSZ[i] * 2.2 / y[i] + 0.5))
        val = int(min(160, 110 * PSZ[i] * min(1.0, 2.0 / y[i] + 0.2)))
        tgt = front if y[i] < Y_PERSON - 0.2 else back
        cv2.line(tgt, (int(u0[i] * 4), int(v0[i] * 4)), (int(u1[i] * 4), int(v1[i] * 4)), val, thick, cv2.LINE_AA, shift=2)
    return back, front, amt

# ------------------------------------------------------------------ ships
@lru_cache(maxsize=3)
def ship_frame(i):
    p = os.path.join(WK, 'ships', 's_%04d.npy' % i)
    if not os.path.exists(p): return None
    im = np.load(p).astype(np.float32)
    a = np.clip(im[..., 3:4], 0, 1); rgb = np.clip(im[..., :3], 0, 25.0 * a)     # kill fireflies
    return np.dstack([rgb, a])
_eng = None
def engines():
    global _eng
    if _eng is None:
        p = os.path.join(WK, 'ships', 'engines.json'); _eng = json.load(open(p)) if os.path.exists(p) else {}
    return _eng
ACC = {'castor': np.array([0.15, 0.85, 1.0], np.float32), 'pollux': np.array([1.0, 0.2, 0.75], np.float32)}

# ------------------------------------------------------------------ finishing
def bloom(img):
    br = np.clip(img - 0.9, 0, None)
    out = np.zeros_like(img); small = br
    for s, wgt in ((4, 0.5), (14, 0.35), (40, 0.25), (110, 0.18)):
        f = max(1, s // 6)
        sm_ = cv2.resize(br, (W // f, H // f), interpolation=cv2.INTER_AREA)
        sm_ = cv2.GaussianBlur(sm_, (0, 0), s / f)
        out += cv2.resize(sm_, (W, H), interpolation=cv2.INTER_LINEAR) * wgt
    streak = cv2.resize(np.clip(img - 2.0, 0, None), (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    streak = cv2.GaussianBlur(streak, (0, 0), sigmaX=60, sigmaY=0.6)
    out += cv2.resize(streak, (W, H)) * np.array([0.35, 0.55, 1.0], np.float32) * 0.6
    return img + out
def finish(img, k):
    img = bloom(img)
    # chromatic aberration (radial)
    c = np.float32(0.0018)
    sx = (GX - CX) * c; sy = (GY - H / 2) * c
    r = cv2.remap(img[..., 0], GX + sx, GY + sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    b = cv2.remap(img[..., 2], GX - sx, GY - sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    img = np.dstack([r, img[..., 1], b])
    vig = 1 - 0.38 * (((GX - CX) / CX) ** 2 * 0.6 + ((GY - H / 2) / (H / 2)) ** 2) ** 1.2
    img *= vig[..., None]
    # soft-clip highlights (keeps the plate's mid-tones untouched)
    knee = 0.78
    img = np.where(img < knee, img, knee + (1 - knee) * (1 - np.exp(-(img - knee) / (1 - knee))))
    g = np.random.default_rng(1000 + k).normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
    out = np.clip(img, 0, 1) ** (1 / 2.2)
    out = out + g[..., None] * 0.018 * (0.4 + 0.6 * (1 - out))
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)

def desat(img, s):
    l = (img * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    return l + (img - l) * s

# ------------------------------------------------------------------ frame
def render(k):
    s = src_time(k)
    Ms = M_at(s); P = shake(k) @ push(k)
    G1 = P @ Ms                     # frame-1 space -> output
    GL = G1 @ A1                    # L canvas -> output
    plate_rgb, al = interp_src(s)
    if not np.allclose(P, np.eye(3)):
        plate_rgb = cv2.warpAffine(plate_rgb, P[:2], (W, H), borderMode=cv2.BORDER_REPLICATE)
        al = cv2.warpAffine(al, P[:2], (W, H))
    st, sp = storm_amt(k), space_amt(k)
    warpL = lambda img, bm=cv2.BORDER_REPLICATE: cv2.warpAffine(img, GL[:2], (W, H), flags=cv2.INTER_LINEAR, borderMode=bm)
    # --- background grade
    bg = plate_rgb.copy()
    storm_look = desat(bg, 0.3) * np.array([1.05, 0.78, 0.55], np.float32) * 0.2 + np.array([0.045, 0.03, 0.018], np.float32)
    bg = lerp(bg, storm_look, st)
    night = desat(plate_rgb, 0.35) * np.array([0.22, 0.26, 0.36], np.float32) * 0.55
    bg = lerp(bg, night, sp)
    # --- sky: space replaces the sky under the dust
    sky_c = None
    if sp > 0 or k >= 118:
        sky_c = space_sky(k)
        skyL = sky_to_L(sky_c)
        sky_f = warpL(skyL)
        skymask = warpL((LV < VH0 + 1.5).astype(np.float32) * sm(VH0 + 2, VH0 - 2, LV), cv2.BORDER_CONSTANT)
        bg = bg * (1 - skymask[..., None]) + sky_f * skymask[..., None]
    # --- dust wall / storm (behind subject): Cycles volume + 2D skirt / inside fog
    vol = dust_vol(k); vveil = None
    if vol is not None:
        D_ = storm_D(k)
        Gd = G1 @ T(CX, VH0) @ np.diag([1.07, 1.07, 1.0]) @ T(-CX, -960.0)   # horizon row 960 -> plate horizon; 7% overscan for camera drift
        vol = cv2.warpAffine(vol, Gd[:2], (W, H))
        if D_ > 2500:                                     # far wall: its base sits beyond the sea horizon (earth curvature)
            hm = warpL(sm(VH0 + 1.5, VH0 - 1.5, LV).astype(np.float32), cv2.BORDER_CONSTANT)
            vol = vol * hm[..., None]
        haze = float(np.clip((D_ - 700) / 6000, 0, 0.5))
        if haze > 0:
            vol[..., :3] = vol[..., :3] * (1 - haze) + vol[..., 3:4] * np.array([0.42, 0.44, 0.48], np.float32) * haze
        dn = noise('dfine', 1024, 1024, 5, 51)
        det = cv2.remap(dn, ((GX * 0.9 - k * 1.5) % 1024).astype(np.float32), ((GY * 0.9 + k * 0.8) % 1024).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        vrgb = vol[..., :3] * (1 + 0.16 * (det[..., None] - 0.5)) * lerp(1.0, 0.62, st); va = vol[..., 3:4]
        bg = vrgb + bg * (1 - va)
        if D_ < Y_PERSON:
            f_ = float(np.clip((Y_PERSON - D_) / 2.2, 0, 1)) * 0.85
            vveil = (vrgb * f_, va * f_)
    dcol, dcov, veilL = dust_layer(k)
    dcol_f, dcov_f, veil_f = warpL(dcol), warpL(dcov), warpL(veilL)
    bg = bg * (1 - dcov_f[..., None]) + dcol_f * dcov_f[..., None]
    # --- water
    if k >= 118 and sky_c is not None:
        sky_blur = cv2.GaussianBlur(np.minimum(sky_c, 6.0), (0, 0), 2.6)
        haze = dust_inside(k)
        sky_blur = sky_blur * (1 - 0.7 * haze) + DUST_LIGHT * 0.3 * haze
        wcol, wal = water_layer(k, sky_blur)
        wal = wal * sm(VH0 + 0.5, VH0 + 3.0, LV)
        wcol_f, wal_f = warpL(wcol), warpL(wal, cv2.BORDER_CONSTANT)
        fade = smf(118, 140, k)
        bg = bg * (1 - wal_f[..., None] * fade) + wcol_f * wal_f[..., None] * fade
    # --- ships + engine trails
    si = k - SHIP_K0 + 1
    if 1 <= si <= 48:
        sh = ship_frame(si)
        if sh is not None:
            sh = cv2.warpAffine(sh, G1[:2], (W, H))
            bg = sh[..., :3] * 1.0 + bg * (1 - sh[..., 3:4])
        eng = engines(); tr = np.zeros((H, W, 3), np.float32)
        for name, frames in eng.items():
            for e in range(2):
                pts = []
                for j in range(max(0, si - 3), si):
                    x, y, zc = frames[j][e]
                    if zc <= 0: continue
                    p = G1 @ np.array([x, y, 1.0]); pts.append((p[0], p[1], j))
                for a_, b_ in zip(pts[:-1], pts[1:]):
                    if math.hypot(b_[0] - a_[0], b_[1] - a_[1]) > 120: continue
                    age = (si - 1 - b_[2]) / 3.0; g = 1.4 * (1 - age) ** 1.5
                    cv2.line(tr, (int(a_[0] * 4), int(a_[1] * 4)), (int(b_[0] * 4), int(b_[1] * 4)), tuple(float(c) for c in ACC[name] * g), 2, cv2.LINE_AA, shift=2)
        tr = cv2.GaussianBlur(tr, (0, 0), 2.5) + cv2.GaussianBlur(tr, (0, 0), 9) * 0.8
        bg += tr
    sand_col0 = np.array([0.55, 0.42, 0.3], np.float32) * lerp(1.0, 0.45, st) * lerp(1.0, 0.5, sp) + np.array([0.25, 0.12, 0.03], np.float32) * sp
    bg = ground_streams(bg, k, GL, sand_col0, 'back')
    # --- subject: relight, waterline cut, sink
    h = level_h(k); sink = sink_p(k)
    bhp = GL @ np.array([540 + MG, 430 + MG, 1.0])          # black hole centre on screen (light source)
    subj = relight(plate_rgb, al, k, (bhp[0], bhp[1]), st, sp)
    dogm = np.zeros((H, W), np.float32)
    db = (G1 @ np.array([[DOG_BOX[0], DOG_BOX[2]], [DOG_BOX[1], DOG_BOX[3]], [1, 1]]))
    x0, x1, y0b, y1b = int(db[0].min()), int(db[0].max()), int(db[1].min()), int(db[1].max())
    dogm[max(y0b, 0):max(y1b, 0), max(x0, 0):max(x1, 0)] = 1
    dogm = cv2.GaussianBlur(dogm, (0, 0), 6)
    a_dog = al * dogm; a_per = al * (1 - dogm)
    def cut_y(Yd):
        vL = VH0 + F * (CAM_H - h) / Yd
        p = GL @ np.array([600 + MG, vL + MG, 1.0]); return p[1]
    out = bg
    for a_obj, Yd, sinkm in ((a_dog, Y_DOG, 0.0), (a_per, Y_PERSON, sink)):
        dv = F * sinkm / Yd
        if dv > 0.5:
            Ms_ = np.float32([[1, 0, 0], [0, 1, dv]])
            a_obj = cv2.warpAffine(a_obj, Ms_, (W, H)); s_rgb = cv2.warpAffine(subj, Ms_, (W, H), borderMode=cv2.BORDER_REPLICATE)
        else: s_rgb = subj
        if h > 0.005 and front_F(k) < Yd + 0.3:
            yc = cut_y(Yd)
            wob = 5 * np.sin(GX * 0.045 + k * 0.5) + 3 * np.sin(GX * 0.11 - k * 0.8)
            above_w = sm(yc + 3 + wob, yc - 3 + wob, GY)
            under = (1 - above_w) * np.exp(-np.clip(GY - yc, 0, None) / 140.0) * 0.35
            refr = cv2.remap(s_rgb, GX + 6 * np.sin(GY * 0.05 + k * 0.4), GY, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            wcol_under = np.array([0.01, 0.05, 0.06], np.float32) * lerp(1.0, 0.35, sp)
            a_under = cv2.remap(a_obj, GX + 6 * np.sin(GY * 0.05 + k * 0.4), GY, cv2.INTER_LINEAR) * under
            out = out * (1 - a_under[..., None]) + (refr * 0.5 + wcol_under) * a_under[..., None]
            a_vis = a_obj * above_w
            bounce = np.exp(-np.clip(yc - GY, 0, None) / 160.0) * above_w * space_amt(k)
            s_lit = s_rgb + bounce[..., None] * np.array([0.04, 0.03, 0.022], np.float32)
            out = out * (1 - a_vis[..., None]) + s_lit * a_vis[..., None]
            # foam collar where the water meets the body
            collar = np.exp(-((GY - yc - wob) / 7.0) ** 2) * cv2.GaussianBlur(a_obj, (0, 0), 10) * 1.4
            out = out * (1 - np.clip(collar, 0, 1)[..., None]) + np.array([0.6, 0.66, 0.7], np.float32) * lerp(1, 0.4, sp) * np.clip(collar, 0, 1)[..., None]
        else:
            out = out * (1 - a_obj[..., None]) + s_rgb * a_obj[..., None]
    # splashes + bubbles (closed-form particle bursts)
    out = splashes(out, k, G1, GL)
    # --- foreground: sand streams + grains + dust veil
    pb, pf, pamt = particles(k, GL)
    sand_col = np.array([0.55, 0.42, 0.3], np.float32) * lerp(1.0, 0.6, st) * lerp(1.0, 0.5, sp) + np.array([0.25, 0.12, 0.03], np.float32) * sp
    if pamt > 0:
        pbb = cv2.GaussianBlur(pb, (0, 0), 0.7).astype(np.float32) / 255.0
        out = out * (1 - pbb[..., None] * 0.6) + sand_col * pbb[..., None] * 0.6
        pfb = cv2.GaussianBlur(pf, (0, 0), 2.2).astype(np.float32) / 255.0
        out = out * (1 - pfb[..., None] * 0.8) + sand_col * 1.1 * pfb[..., None] * 0.8
        out = ground_streams(out, k, GL, sand_col, 'front')
    out = out * (1 - veil_f[..., None]) + dcol_f * veil_f[..., None]
    if vveil is not None:
        out = vveil[0] + out * (1 - vveil[1])
    inside = dust_inside(k)
    if inside > 0.02:
        out = lerp(out, dcol_f * 0.9, np.float32(0.35 * inside))
    if 150 <= k <= 156:
        out = out + np.float32(0.25 * math.exp(-((k - 152) / 1.5) ** 2))   # sonic-boom flash
    return finish(out, k)

LUMW = np.array([0.2126, 0.7152, 0.0722], np.float32)
def relight(rgb, al, k, light_xy, st, sp):
    """Relight the daylight plate subject for the storm and for the black-hole night.
    Removes the sun look (highlight compression, desaturation), adds a cool sky fill and a warm
    backlight rim whose strength follows the matte's edge normal facing the light."""
    lum = (rgb * LUMW).sum(-1, keepdims=True)
    # daylight -> flat, highlight-compressed base (kills the hard sun key on the face/shirt)
    comp_ = lum / (1 + 1.6 * lum) * 1.9
    flat = desat(rgb, 0.55) * (comp_ / np.maximum(lum, 1e-4))
    # edge normals from the matte
    a8 = cv2.GaussianBlur(al, (0, 0), 7)
    gx = cv2.Sobel(a8, cv2.CV_32F, 1, 0, ksize=5); gy = cv2.Sobel(a8, cv2.CV_32F, 0, 1, ksize=5)
    gl = np.sqrt(gx * gx + gy * gy) + 1e-6
    nx, ny = -gx / gl, -gy / gl
    lx, ly = light_xy[0] - GX, light_xy[1] - GY; ll = np.sqrt(lx * lx + ly * ly) + 1e-6
    facing = np.clip((nx * lx + ny * ly) / ll, 0, 1)
    up = np.clip(-ny, 0, 1)
    thin = np.clip(al - cv2.erode(al, np.ones((7, 7), np.uint8)), 0, 1)
    wide = np.clip((al - cv2.GaussianBlur(al, (0, 0), 16)) * 2.2, 0, 1)
    edge_lum = np.clip(lum[..., 0] * 2.5, 0.25, 1.4)                       # white fur / hair / shirt glow more
    rim = (facing ** 1.4 * 0.75 + up * 0.35) * (thin * 1.5 + wide * 0.55) * edge_lum
    rim = cv2.GaussianBlur(rim, (0, 0), 1.0) * al
    out = rgb
    if st > 0:   # dust storm: dim, warm, low contrast, soft back-scatter from the bright dust behind
        storm = flat * np.array([0.95, 0.72, 0.52], np.float32) * 0.34 + 0.03 * np.array([0.6, 0.45, 0.3], np.float32)
        storm = storm + rim[..., None] * np.array([0.55, 0.38, 0.22], np.float32) * 0.5
        out = lerp(out, storm, st)
    if sp > 0:   # night under the black hole: cool sky fill + strong golden backlight
        flick = 1 + 0.04 * math.sin(k * 0.37) + 0.025 * math.sin(k * 1.3)
        night = flat * np.array([0.036, 0.046, 0.072], np.float32) + 0.003
        night = night + rim[..., None] * np.array([1.9, 1.15, 0.52], np.float32) * flick
        night = night + (wide * facing)[..., None] * np.array([0.10, 0.06, 0.03], np.float32) * edge_lum[..., None]
        out = lerp(out, night, sp)
    return out.astype(np.float32)

def ground_streams(out, k, GL, col, which):
    """Wind-blown sand snaking along the beach. Ground beyond the subject is drawn behind it, nearer ground in front."""
    amt = smf(15, 60, k) * (1 - smf(185, 200, k))
    if amt <= 0: return out
    n = noise('stream', 512, 2048, 7, 41); wv = noise('d2', 1024, 1024, 7, 22)
    wob = cv2.remap(wv, ((LU * 0.6 + k * 4) % 1024).astype(np.float32), ((LV * 0.6) % 1024).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) - 0.5
    u = ((LU * 0.5 + k * 30.0) % 2048).astype(np.float32); v = ((LV * 3.2 + wob * 90) % 512).astype(np.float32)
    s = cv2.remap(n, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    band = sm(VH0 + 230, VH0 + 520, LV)
    depth = sm(Y_PERSON - 0.15, Y_PERSON + 0.15, Yg)
    side = depth if which == 'back' else 1 - depth
    a = np.clip((s - 0.5) * 2.6, 0, 1) ** 1.5 * band * side * amt * 0.32 * (1 - 0.6 * space_amt(k))
    a = cv2.GaussianBlur(a, (0, 0), 1.6)
    a_f = cv2.warpAffine(a, GL[:2], (W, H))
    return out * (1 - a_f[..., None]) + col * 1.1 * a_f[..., None]

rng_s = np.random.default_rng(17)
def splashes(out, k, G1, GL):
    events = [(186, 330, 1.0, Y_DOG, 0.15), (190, 610, 1.3, Y_PERSON, 0.2), (262, 600, 1.6, Y_PERSON, 0.95)]
    lay = np.zeros((H, W), np.uint8)
    for (k0_, ux, power, Yd, hz) in events:
        dt = (k - k0_) / FPS
        if dt < 0 or dt > 1.4: continue
        r = np.random.default_rng(k0_)
        n = int(500 * power)
        vx = r.normal(0, 1.6, n) * power; vz = r.uniform(1.5, 5.5, n) * power; vy = r.normal(0, 0.6, n)
        x = vx * dt; z = hz + vz * dt - 4.9 * dt * dt; y = Yd + vy * dt
        ok = z > hz - 0.05
        X0 = (ux - CX) * Yd / F
        uu = CX + F * (X0 + x) / y; vv = VH0 + F * (CAM_H - z) / y
        p = GL @ np.vstack([uu + MG, vv + MG, np.ones_like(uu)])
        sz = r.uniform(1, 4, n)
        for i in np.nonzero(ok)[0]:
            cv2.circle(lay, (int(p[0, i] * 4), int(p[1, i] * 4)), int(sz[i] * 4 * (1 - dt / 1.6)), 220, -1, cv2.LINE_AA, shift=2)
    if k >= 262:   # bubbles rising where the subject went under
        r = np.random.default_rng(99); n = 80
        t0 = r.uniform(262, 290, n); xs = r.normal(600, 60, n)
        for i in range(n):
            dt = (k - t0[i]) / FPS
            if dt < 0 or dt > 0.9: continue
            yc = VH0 + F * (CAM_H - level_h(k)) / Y_PERSON
            vv = yc + 150 - dt * 180 + 10 * math.sin(dt * 9 + i)
            if vv < yc: continue
            p = GL @ np.array([xs[i] + MG, vv + MG, 1.0])
            cv2.circle(lay, (int(p[0] * 4), int(p[1] * 4)), int(4 * (2 + i % 5)), 150, 2, cv2.LINE_AA, shift=2)
    if lay.any():
        a = cv2.GaussianBlur(lay.astype(np.float32) / 255.0, (0, 0), 0.8)
        col = np.array([0.8, 0.86, 0.9], np.float32) * lerp(1, 0.45, space_amt(k)) + np.array([0.25, 0.15, 0.05], np.float32) * space_amt(k)
        out = out * (1 - a[..., None]) + col * a[..., None]
    return out

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    od = os.path.join(WK, 'out'); os.makedirs(od, exist_ok=True)
    import time
    for k in range(a, b + 1):
        t0 = time.time()
        img = render(k)
        cv2.imwrite(os.path.join(od, 'f_%04d.png' % k), img[..., ::-1])
        print('frame', k, '%.1fs' % (time.time() - t0), flush=True)
