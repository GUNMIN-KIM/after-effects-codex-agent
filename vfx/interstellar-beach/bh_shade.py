# Shade the traced black-hole maps: animated accretion disk + lensed starfield/nebula. Linear HDR output.
import numpy as np, os, cv2
SP = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(7)

def fbm_tex(h, w, octaves=7, seed=0, wrap=True):
    g = np.random.default_rng(seed); out = np.zeros((h, w), np.float32); amp = 1.0; tot = 0
    for o in range(octaves):
        sh, sw = max(2, h >> (octaves - o)), max(2, w >> (octaves - o))
        n = g.random((sh, sw)).astype(np.float32)
        if wrap: n = np.concatenate([n, n[:, :1]], 1)
        up = cv2.resize(n, (w + (1 if wrap else 0), h), interpolation=cv2.INTER_CUBIC)[:, :w]
        out += up * amp; tot += amp; amp *= 0.55
    out /= tot
    return (out - out.min()) / (out.max() - out.min())

def star_map(esc, R=1400, density=0.05, sigma=0.24):
    """Crisp procedural stars hashed on a cube map, evaluated at each pixel's escape direction (lensing included)."""
    d = esc.reshape(-1, 3).astype(np.float64); a = np.abs(d); f = np.argmax(a, axis=1)
    n = np.arange(len(d)); m = a[n, f]
    u = np.where(f == 0, d[:, 1], d[:, 0]) / m
    v = np.where(f == 2, d[:, 1], d[:, 2]) / m
    face = (f * 2 + (d[n, f] > 0)).astype(np.uint64)
    gu = (u * 0.5 + 0.5) * R; gv = (v * 0.5 + 0.5) * R
    iu = np.floor(gu).astype(np.int64); iv = np.floor(gv).astype(np.int64)
    def hsh(x):
        x = (x ^ (x >> np.uint64(33))) * np.uint64(0xff51afd7ed558ccd)
        x = (x ^ (x >> np.uint64(33))) * np.uint64(0xc4ceb9fe1a85ec53)
        return x ^ (x >> np.uint64(33))
    with np.errstate(over='ignore'):
        base = face * np.uint64(0x9E3779B97F4A7C15) + iu.astype(np.uint64) * np.uint64(0x85EBCA6B) + iv.astype(np.uint64) * np.uint64(0xC2B2AE35)
        h1 = hsh(base); h2 = hsh(h1 + np.uint64(1)); h3 = hsh(h1 + np.uint64(2)); h4 = hsh(h1 + np.uint64(3)); h5 = hsh(h1 + np.uint64(4))
    to01 = lambda x: (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)
    r1, r2, r3, r4, r5 = map(to01, (h1, h2, h3, h4, h5))
    sx, sy = 0.25 + 0.5 * r2, 0.25 + 0.5 * r3
    d2 = (gu - iu - sx) ** 2 + (gv - iv - sy) ** 2
    b = np.clip(0.004 / (r4 + 0.0015) ** 1.15, 0, 9.0)
    val = (r1 < density) * b * np.exp(-d2 / (2 * sigma ** 2))
    col = np.stack([0.8 + 0.4 * r5, 0.85 + 0.1 * r5, 1.2 - 0.5 * r5], 1)
    return (val[:, None] * col).reshape(esc.shape).astype(np.float32)

def sky_texture(h=2048, w=4096):
    """Equirect starfield with a dusty galactic band and coloured nebula."""
    path = os.path.join(SP, 'work', 'sky_%dx%d.npy' % (w, h))
    if os.path.exists(path): return np.load(path)
    lat = (0.5 - (np.arange(h) + 0.5) / h)[:, None] * np.pi
    lon = ((np.arange(w) + 0.5) / w * 2 - 1)[None, :] * np.pi
    band = np.exp(-((lat - 0.35 * np.sin(lon * 1.0 + 0.6)) / 0.22) ** 2)
    n1, n2, n3 = fbm_tex(h, w, 8, 1), fbm_tex(h, w, 8, 2), fbm_tex(h, w, 6, 3)
    dust = np.clip((n2 - 0.45) * 2.2, 0, 1)
    glow = band * (0.25 + 0.9 * n1 ** 2) * (1 - 0.85 * dust)
    sky = np.zeros((h, w, 3), np.float32)
    sky += glow[..., None] * np.array([0.13, 0.12, 0.15], np.float32) * 0.32
    neb = np.clip((n3 - 0.55) * 3, 0, 1) ** 1.5 * band
    sky += neb[..., None] * np.array([0.08, 0.16, 0.42], np.float32) * 0.3
    sky += (np.clip((n1 - 0.6) * 3, 0, 1) ** 2 * band)[..., None] * np.array([0.45, 0.10, 0.22], np.float32) * 0.12
    # stars: power-law brightness, denser in the band
    cnt = 0
    ys = rng.random(cnt); xs = rng.random(cnt)
    lat_s = (0.5 - ys) * np.pi
    keep = rng.random(cnt) < (0.25 + 0.75 * np.exp(-((lat_s - 0.35 * np.sin((xs * 2 - 1) * np.pi + 0.6)) / 0.3) ** 2)) * np.cos(lat_s)
    ys, xs = ys[keep], xs[keep]
    b = (rng.pareto(1.6, ys.size) + 1) * 0.04
    temp = rng.random(ys.size)
    col = np.stack([0.75 + 0.45 * temp, 0.8 + 0.1 * temp, 1.15 - 0.5 * temp], 1)
    yi, xi = (ys * h).astype(int), (xs * w).astype(int)
    np.add.at(sky, (yi, xi), (b[:, None] * col).astype(np.float32))
    bright = b > 0.6
    for y, x, bb, c in zip(yi[bright], xi[bright], b[bright], col[bright]):
        r = int(min(6, 1 + bb * 2))
        cv2.circle(sky, (int(x), int(y)), r, tuple(float(v) for v in c * bb * 0.08), -1, lineType=cv2.LINE_AA)
    sky = cv2.GaussianBlur(sky, (0, 0), 0.6)
    np.save(path, sky)
    return sky

class BlackHole:
    def __init__(self, maps):
        d = np.load(maps)
        self.hit, self.r, self.phi, self.side = d['hit'], d['r'], d['phi'], d['side']
        self.hit2, self.r2, self.phi2 = d['hit2'], d['r2'], d['phi2']
        self.esc, self.cap = d['esc'], d['cap']
        self.sky = sky_texture()
        e = self.esc
        lon = np.arctan2(e[..., 0], -e[..., 2]); lat = np.arcsin(np.clip(e[..., 1], -1, 1))
        sh, sw = self.sky.shape[:2]
        self.mapx = ((lon / np.pi + 1) / 2 * sw).astype(np.float32) % sw
        self.mapy = ((0.5 - lat / np.pi) * sh).astype(np.float32)
        self.disk_noise = fbm_tex(512, 2048, 8, 11)        # (log r, angle)
        sp_ = maps.replace('.npz', '_stars.npy')
        if os.path.exists(sp_): self.stars = np.load(sp_)
        else: self.stars = star_map(self.esc); np.save(sp_, self.stars)
        self.stars[self.cap] = 0
        self.disk_fine = fbm_tex(1024, 1024, 6, 12)

    def disk(self, r, phi, t, side):
        R_IN, R_OUT = 6.0, 24.0
        x = (np.log(r / R_IN) / np.log(R_OUT / R_IN))           # 0..1 across the disk
        omega = 0.9 * (6.0 / r) ** 1.5                            # keplerian shear
        ang = (phi - omega * t) / (2 * np.pi) % 1.0
        ny = np.clip(x, 0, 1) * 511; nx = ang * 2047
        n = cv2.remap(self.disk_noise, nx.astype(np.float32), ny.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        rings = 0.5 + 0.5 * np.sin(x * 70 + n * 6.0)
        streak = cv2.remap(self.disk_fine, (ang * 1023 * 3 % 1023).astype(np.float32), (x * 1023).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        dens = (0.3 + 0.7 * n ** 1.3) * (0.82 + 0.18 * rings) * (0.72 + 0.4 * streak)
        temp = (6.0 / r) ** 0.75 * np.clip(1 - np.sqrt(6.0 / r), 0, 1) ** 0.25 * 1.9
        edge = np.clip((r - R_IN) / 0.6, 0, 1) * np.clip((R_OUT - r) / 6.0, 0, 1)
        # doppler beaming: approaching side (phi ~ +pi/2 here) brighter
        beta = np.sqrt(1.0 / (r - 2.0))
        g = 1.0 / (1.0 - 0.55 * beta * np.sin(phi))
        grav = np.sqrt(np.clip(1 - 3.0 / r, 0.05, 1))
        I = dens * temp * edge * g ** 2.6 * grav
        # colour ramp: white-hot -> gold -> amber -> deep red
        c_hot = np.array([1.0, 0.93, 0.82]); c_mid = np.array([1.0, 0.62, 0.25]); c_cool = np.array([0.75, 0.22, 0.06])
        tt = np.clip(temp * g * 0.9, 0, 1.4)[..., None]
        col = np.where(tt > 0.6, c_mid + (c_hot - c_mid) * np.clip((tt - 0.6) / 0.5, 0, 1), c_cool + (c_mid - c_cool) * np.clip(tt / 0.6, 0, 1))
        return (I[..., None] * col * 3.4).astype(np.float32)

    def render(self, t, disk_gain=1.0, star_gain=1.0):
        bg = cv2.remap(self.sky, self.mapx, self.mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) + self.stars * star_gain
        out = bg.copy()
        h2 = self.hit2 & ~self.hit
        if h2.any(): pass
        d2 = self.disk(np.where(self.hit2, self.r2, 10.0), self.phi2, t, 0)
        out = np.where(self.hit2[..., None], out * 0.15 + d2 * 0.9, out)
        d1 = self.disk(np.where(self.hit, self.r, 10.0), self.phi, t, 0)
        alpha = 0.93
        out = np.where(self.hit[..., None], out * (1 - alpha) + d1 * disk_gain, out)
        out[self.cap & ~self.hit] = 0.0
        return out

if __name__ == '__main__':
    import sys
    maps = sys.argv[1]
    bh = BlackHole(maps)
    img = bh.render(0.0)
    tm = img / (1 + img)          # quick look tonemap
    cv2.imwrite(os.path.join(SP, '..', 'shots', 'bh_test.png'), (np.clip(tm, 0, 1) ** (1 / 2.2) * 255)[..., ::-1].astype(np.uint8))
