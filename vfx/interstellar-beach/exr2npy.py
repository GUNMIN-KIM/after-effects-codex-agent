import bpy, numpy as np, glob, os
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'ships')
for p in sorted(glob.glob(os.path.join(d, 's_*.exr'))):
    img = bpy.data.images.load(p); w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]
    np.save(p.replace('.exr', '.npy'), a.astype(np.float16)); bpy.data.images.remove(img)
print('converted')
