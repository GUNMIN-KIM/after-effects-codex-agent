import numpy as np, os
from PIL import Image
from ultralytics import SAM
SP = os.path.dirname(os.path.abspath(__file__))
os.chdir(os.path.join(SP, 'work'))
model = SAM('sam2.1_l.pt')
src = os.path.join(SP, 'plate', 'p_0001.png')
res = model(src, bboxes=[[425, 680, 775, 1725], [145, 1445, 420, 1695], [640, 1000, 775, 1205]], verbose=False)[0]
m = res.masks.data.cpu().numpy().astype(bool)          # (n, H, W)
print('masks', m.shape, [int(x.sum()) for x in m])
final = m.any(0)
img = np.array(Image.open(src).convert('RGB'))
Image.fromarray((final * 255).astype(np.uint8)).save(os.path.join(SP, 'work', 'mask0.png'))
vis = img.astype(np.float32); vis[~final] *= 0.25; vis[final] = vis[final] * 0.6 + np.array([0, 255, 120]) * 0.4
Image.fromarray(vis.astype(np.uint8)).resize((540, 960)).save(os.path.join(SP, '..', 'shots', 'mask0_vis.png'))
