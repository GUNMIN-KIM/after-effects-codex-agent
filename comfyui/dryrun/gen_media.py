import av, numpy as np, sys, os
from fractions import Fraction
from PIL import Image

def code_color(i):
    return np.array([(i % 16) / 15.0, ((i // 16) % 16) / 15.0, 0.5])

def frame(i, w, h, n):
    y, x = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3))
    img[..., 0] = x / w; img[..., 1] = y / h; img[..., 2] = 0.3
    # code block: left third, vertically centered band
    img[h//4:3*h//4, :w//3] = code_color(i)
    # moving white square on the right
    s = max(8, h // 8)
    cx = int(w/3 + (w*2/3 - s) * (i / max(1, n-1)))
    img[h//2 - s//2:h//2 + s//2, cx:cx+s] = 1.0
    return (img * 255).round().astype(np.uint8)

def mask_frame(i, w, h, n):
    y, x = np.mgrid[0:h, 0:w]
    cx = w * (0.55 + 0.3 * i / max(1, n-1)); cy = h * 0.5; r = min(w, h) * 0.18
    m = ((x - cx)**2 + (y - cy)**2) < r*r
    img = np.zeros((h, w, 3), np.uint8); img[m, 0] = 255  # red channel = mask
    return img

def write(path, w, h, n, fps, kind="src", audio=True):
    c = av.open(path, "w")
    v = c.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001))
    v.width, v.height, v.pix_fmt = w, h, "yuv420p"; v.options = {"crf": "1", "preset": "ultrafast"}
    a = None
    if audio:
        a = c.add_stream("aac", rate=48000); a.layout = "stereo"
    for i in range(n):
        img = frame(i, w, h, n) if kind == "src" else mask_frame(i, w, h, n)
        for p in v.encode(av.VideoFrame.from_ndarray(img, format="rgb24")): c.mux(p)
    for p in v.encode(): c.mux(p)
    if a:
        sr = 48000; dur = n / fps; t = np.arange(int(sr * dur)) / sr
        s = (0.2 * np.sin(2*np.pi*440*t)).astype(np.float32)
        for k in range(0, len(s), 1024):
            chunk = np.stack([s[k:k+1024]]*2)
            af = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo"); af.sample_rate = sr; af.pts = k
            for p in a.encode(af): c.mux(p)
        for p in a.encode(): c.mux(p)
    c.close()

def ref(path, w, h):
    y, x = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3)); img[..., 2] = 0.8; img[h//5:4*h//5, w//3:2*w//3] = [0.9, 0.3, 0.1]
    Image.fromarray((img*255).astype(np.uint8)).save(path)

if __name__ == "__main__":
    d = sys.argv[1]; os.makedirs(d, exist_ok=True)
    write(f"{d}/drv_land_170f_30.mp4", 640, 360, 170, 30)
    write(f"{d}/drv_port_50f_24.mp4", 360, 640, 50, 24)
    write(f"{d}/drv_land_100f_25.mp4", 640, 360, 100, 25)
    write(f"{d}/src_land_50f_30.mp4", 640, 360, 50, 30)
    write(f"{d}/mask_land_50f_30.mp4", 640, 360, 50, 30, kind="mask", audio=False)
    write(f"{d}/mask_land_40f_30.mp4", 640, 360, 40, 30, kind="mask", audio=False)
    write(f"{d}/src_port_33f_24.mp4", 360, 640, 33, 24)
    write(f"{d}/mask_port_33f_24.mp4", 360, 640, 33, 24, kind="mask", audio=False)
    write(f"{d}/src_hd_17f_2997.mp4", 1920, 1080, 17, 30000/1001)
    write(f"{d}/mask_hd_17f_2997.mp4", 1920, 1080, 17, 30000/1001, kind="mask", audio=False)
    ref(f"{d}/ref_portrait.png", 512, 768)
    print("ok")
