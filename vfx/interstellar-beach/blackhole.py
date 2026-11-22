# Schwarzschild black hole with a thin accretion disk.
# Pass 1 (expensive, once): integrate null geodesics for every pixel, store where each ray ends
#   (disk hit radius/angle/which side, escape direction, or capture) -> work/bh_maps.npz
# Pass 2 (cheap, per frame): shade the maps with an animated disk texture and a starfield.
# Units: G = M = c = 1, Schwarzschild radius Rs = 2. Photon path: x'' = -1.5 h^2 x / r^5  (h = |x cross v|).
import numpy as np, os, sys, time
SP = os.path.dirname(os.path.abspath(__file__))
W = int(sys.argv[1]) if len(sys.argv) > 1 else 1600
H = int(sys.argv[2]) if len(sys.argv) > 2 else 1600
OUT = os.path.join(SP, 'work', 'bh_maps_%dx%d.npz' % (W, H))

R_IN, R_OUT = 6.0, 24.0          # disk inner/outer radius (ISCO = 6M)
CAM_R, INCL = 90.0, np.radians(86.5)   # observer distance; polar angle from the disk normal
FOV = np.radians(76.2)

def basis():
    # disk normal = +y. camera on the (x,y) plane, slightly above the disk
    cam = np.array([0.0, CAM_R * np.cos(INCL), -CAM_R * np.sin(INCL)])
    fwd = -cam / np.linalg.norm(cam)
    up0 = np.array([0.0, 1.0, 0.0]); right = np.cross(fwd, up0); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    roll = np.radians(-7.0)  # tilt the disk for drama
    r2 = right * np.cos(roll) + up * np.sin(roll); u2 = up * np.cos(roll) - right * np.sin(roll)
    return cam, fwd, r2, u2

def trace():
    cam, fwd, right, up = basis()
    aspect = W / H
    xs = (np.arange(W) + 0.5) / W * 2 - 1; ys = 1 - (np.arange(H) + 0.5) / H * 2
    tx = np.tan(FOV / 2) * aspect if aspect < 1 else np.tan(FOV / 2)
    ty = tx / aspect
    X, Y = np.meshgrid(xs * tx, ys * ty)
    dirs = fwd[None, None] + X[..., None] * right + Y[..., None] * up
    dirs = (dirs / np.linalg.norm(dirs, axis=-1, keepdims=True)).reshape(-1, 3).astype(np.float64)
    N = dirs.shape[0]
    hit_r = np.zeros(N, np.float32); hit_phi = np.zeros(N, np.float32); hit_side = np.zeros(N, np.int8)
    hit_order = np.zeros(N, np.int8)             # 1 = direct image, 2+ = lensed (higher order) image
    esc = np.zeros((N, 3), np.float32); captured = np.zeros(N, bool); hit = np.zeros(N, bool)
    hit2_r = np.zeros(N, np.float32); hit2_phi = np.zeros(N, np.float32); hit2 = np.zeros(N, bool)
    CH = 60000
    t0 = time.time()
    for s in range(0, N, CH):
        d = dirs[s:s + CH]; n = d.shape[0]
        x = np.repeat(cam[None], n, 0); v = d.copy()
        h2 = np.sum(np.cross(x, v) ** 2, axis=1)[:, None]
        alive = np.ones(n, bool); crossings = np.zeros(n, np.int8)
        lr, lp, l2r, l2p, lh, lh2 = (np.zeros(n, np.float32) for _ in range(6))
        lhit = np.zeros(n, bool); lhit2 = np.zeros(n, bool)
        lside = np.zeros(n, np.int8)
        for it in range(1400):
            idx = np.nonzero(alive)[0]
            if idx.size == 0: break
            xi, vi, hi = x[idx], v[idx], h2[idx]
            r = np.linalg.norm(xi, axis=1)
            dt = np.clip(0.05 * r, 0.03, 2.5)[:, None]          # adaptive step: small near the hole
            def acc(p):
                rr = np.linalg.norm(p, axis=1)[:, None]
                return -1.5 * hi * p / rr ** 5
            k1v = acc(xi); k1x = vi
            k2v = acc(xi + 0.5 * dt * k1x); k2x = vi + 0.5 * dt * k1v
            k3v = acc(xi + 0.5 * dt * k2x); k3x = vi + 0.5 * dt * k2v
            k4v = acc(xi + dt * k3x); k4x = vi + dt * k3v
            nx = xi + dt / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
            nv = vi + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
            # disk plane crossing (y changes sign)
            cross = np.sign(xi[:, 1]) != np.sign(nx[:, 1])
            if cross.any():
                f = xi[cross, 1] / (xi[cross, 1] - nx[cross, 1])
                p = xi[cross] + (nx[cross] - xi[cross]) * f[:, None]
                rr = np.hypot(p[:, 0], p[:, 2])
                ok = (rr > R_IN) & (rr < R_OUT)
                ci = idx[cross][ok]
                first = ~lhit[ci]
                c1 = ci[first]; c2 = ci[~first & ~lhit2[ci]]
                pr, pp = rr[ok], np.arctan2(p[ok, 2], p[ok, 0])
                sd = np.where(xi[cross][ok, 1] > 0, 1, -1).astype(np.int8)
                lr[c1] = pr[first]; lp[c1] = pp[first]; lhit[c1] = True; lside[c1] = sd[first]
                sel2 = (~first) & (~lhit2[ci])
                l2r[c2] = pr[sel2]; l2p[c2] = pp[sel2]; lhit2[c2] = True
            x[idx], v[idx] = nx, nv
            rn = np.linalg.norm(nx, axis=1)
            dead = (rn < 2.02) | (rn > 400.0)
            cap = rn < 2.02
            gi = idx[dead]
            captured[s + gi[cap[dead]]] = True
            alive[gi] = False
        vv = v / np.linalg.norm(v, axis=1, keepdims=True)
        esc[s:s + n] = vv; hit[s:s + n] = lhit; hit_r[s:s + n] = lr; hit_phi[s:s + n] = lp; hit_side[s:s + n] = lside
        hit2[s:s + n] = lhit2; hit2_r[s:s + n] = l2r; hit2_phi[s:s + n] = l2p
        print('rays %d/%d  %.0fs' % (s + n, N, time.time() - t0), flush=True)
    np.savez_compressed(OUT, W=W, H=H, hit=hit.reshape(H, W), r=hit_r.reshape(H, W), phi=hit_phi.reshape(H, W), side=hit_side.reshape(H, W),
                        hit2=hit2.reshape(H, W), r2=hit2_r.reshape(H, W), phi2=hit2_phi.reshape(H, W),
                        esc=esc.reshape(H, W, 3), cap=captured.reshape(H, W))
    print('saved', OUT)

if __name__ == '__main__':
    trace()
