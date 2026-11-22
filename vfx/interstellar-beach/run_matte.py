# MatAnyone2 video matting on the plate frames (CPU). Writes 8-bit alpha PNGs.
import os, sys, glob, time, numpy as np, torch, cv2
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ext', 'MatAnyone2'))
from matanyone2.utils.inference_utils import gen_dilate, gen_erosion
from matanyone2.inference.inference_core import InferenceCore
from matanyone2.utils.get_default_model import get_matanyone2_model
SP = os.path.dirname(os.path.abspath(__file__))
torch.set_num_threads(4)
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 9
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
out_dir = os.path.join(SP, 'work', 'alpha'); os.makedirs(out_dir, exist_ok=True)
files = sorted(glob.glob(os.path.join(SP, 'plate', 'p_*.png')))[:LIMIT]
model = get_matanyone2_model(os.path.join(SP, '..', 'ext', 'MatAnyone2', 'pretrained_models', 'matanyone2.pth'), torch.device('cpu'))
proc = InferenceCore(model, cfg=model.cfg)
mask = np.array(Image.open(os.path.join(SP, 'work', 'mask0.png')).convert('L'))
mask = gen_erosion(gen_dilate(mask, 10, 10), 10, 10)
H, W = mask.shape; h, w = int(round(H * SCALE / 16) * 16), int(round(W * SCALE / 16) * 16)
def load(f):
    im = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB)
    if (h, w) != (H, W): im = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
    return torch.from_numpy(im).permute(2, 0, 1).float() / 255.
m = torch.from_numpy(cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)).float()
n_warm = 10; t0 = time.time()
with torch.inference_mode():
    first = load(files[0])
    for ti in range(n_warm + len(files)):
        img = first if ti < n_warm else load(files[ti - n_warm])
        if ti == 0:
            proc.step(img, m, objects=[1]); prob = proc.step(img, first_frame_pred=True)
        elif ti <= n_warm:
            prob = proc.step(img, first_frame_pred=True)
        else:
            prob = proc.step(img)
        a = proc.output_prob_to_mask(prob).cpu().numpy()
        if ti >= n_warm:
            k = ti - n_warm
            if (h, w) != (H, W): a = cv2.resize(a, (W, H), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(os.path.join(out_dir, 'a_%04d.png' % (k + 1)), np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8))
            if k % 10 == 0: print('frame', k + 1, 'of', len(files), '%.1fs elapsed' % (time.time() - t0), flush=True)
print('done', time.time() - t0)
