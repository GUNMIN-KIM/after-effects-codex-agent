import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comp
ks = [int(x) for x in sys.argv[1].split(',')]
ims = []
for k in ks:
    t = time.time(); im = comp.render(k); print(k, '%.1fs' % (time.time() - t), flush=True)
    cv2.imwrite(os.path.join(comp.WK, 'test_%04d.png' % k), im[..., ::-1])
    ims.append(cv2.resize(im, (360, 640), interpolation=cv2.INTER_AREA))
cv2.imwrite(os.path.join(comp.SP, '..', 'shots', sys.argv[2] if len(sys.argv) > 2 else 'comp_test.png'), np.hstack(ims)[..., ::-1])
