# 2D matchmove: per-frame similarity transform (relative to frame 1) from static sand + sky features, and horizon line.
import cv2, numpy as np, json, glob, os
SP = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(SP, 'plate', 'p_*.png')))
H, W = 1920, 1080
mask = np.zeros((H, W), np.uint8)
mask[1450:1880, :] = 255          # sand foreground (static)
mask[40:820, :] = 255             # sky / clouds (far, rotation-like)
mask[600:1760, 400:800] = 0       # person
mask[1420:1720, 120:440] = 0      # dog
prev = cv2.cvtColor(cv2.imread(files[0]), cv2.COLOR_BGR2GRAY)
p0 = cv2.goodFeaturesToTrack(prev, 1500, 0.004, 9, mask=mask, blockSize=9)
ref_pts = p0.copy(); M_list = [np.eye(3).tolist()]
cur_pts = p0.copy(); alive = np.ones(len(p0), bool)
for f in files[1:]:
    g = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY)
    nxt, st, err = cv2.calcOpticalFlowPyrLK(prev, g, cur_pts, None, winSize=(31, 31), maxLevel=4)
    back, st2, _ = cv2.calcOpticalFlowPyrLK(g, prev, nxt, None, winSize=(31, 31), maxLevel=4)
    fb = np.linalg.norm(back - cur_pts, axis=2).ravel()
    alive &= (st.ravel() == 1) & (st2.ravel() == 1) & (fb < 0.8)
    A, inl = cv2.estimateAffinePartial2D(ref_pts[alive], nxt[alive], method=cv2.RANSAC, ransacReprojThreshold=2.0)
    M = np.vstack([A, [0, 0, 1]]); M_list.append(M.tolist())
    cur_pts, prev = nxt, g
# horizon: sky->sea drop of (blue - green), measured left and right of the subject, then smoothed over time
hz = []
for f in files:
    im = cv2.imread(f).astype(np.float32); pts = []
    for x0, x1 in ((20, 380), (830, 1060)):
        bg = (im[900:1020, x0:x1, 0] - im[900:1020, x0:x1, 1]).mean(1)
        d = np.diff(cv2.GaussianBlur(bg.reshape(-1, 1), (1, 5), 0).ravel())
        pts.append(((x0 + x1) / 2, 900 + int(np.argmin(d)) + 0.5))
    (xa, ya), (xb, yb) = pts; k = (yb - ya) / (xb - xa); hz.append([k, ya - k * xa])
hz = np.array(hz)
from scipy.ndimage import gaussian_filter1d
hz = np.stack([gaussian_filter1d(hz[:, 0], 3), gaussian_filter1d(hz[:, 1], 3)], 1).tolist()
A = np.array(M_list)
print('frames', len(M_list), 'tx range', A[:, 0, 2].min().round(1), A[:, 0, 2].max().round(1), 'ty range', A[:, 1, 2].min().round(1), A[:, 1, 2].max().round(1),
      'rot deg', np.degrees(np.arctan2(A[:, 1, 0], A[:, 0, 0])).min().round(2), np.degrees(np.arctan2(A[:, 1, 0], A[:, 0, 0])).max().round(2), 'alive', int(alive.sum()))
hzA = np.array(hz); print('horizon y@540', (hzA[:, 0] * 540 + hzA[:, 1]).min().round(1), (hzA[:, 0] * 540 + hzA[:, 1]).max().round(1), 'tilt deg', np.degrees(np.arctan(hzA[:, 0])).mean().round(2))
json.dump({'M': M_list, 'horizon': hz}, open(os.path.join(SP, 'work', 'track.json'), 'w'))
