# Sound design for the 10 s VFX shot (48 kHz stereo WAV). Times match comp.py (frame / 30).
import numpy as np, os, subprocess
from scipy import signal
from scipy.io import wavfile
SP = os.path.dirname(os.path.abspath(__file__)); WK = os.path.join(SP, 'work')
SR = 48000; DUR = 10.0; N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(3)
def env(points):                      # piecewise-linear envelope [(time, value), ...]
    xs, ys = zip(*points); return np.interp(t, xs, ys)
def noise(n=N): return rng.standard_normal(n)
def bp(x, lo, hi, order=2): return signal.sosfilt(signal.butter(order, [lo, hi], 'bandpass', fs=SR, output='sos'), x)
def lp(x, f, order=2): return signal.sosfilt(signal.butter(order, f, 'lowpass', fs=SR, output='sos'), x)
def hp(x, f, order=2): return signal.sosfilt(signal.butter(order, f, 'highpass', fs=SR, output='sos'), x)
def pan(x, p): return np.stack([x * np.sqrt(0.5 * (1 - p)), x * np.sqrt(0.5 * (1 + p))], 1)
def sweep_bp(x, f0, f1, q=1.5, seg=2048):
    out = np.zeros_like(x); f = np.geomspace(f0, f1, len(x) // seg + 1); zi = None
    for i, s in enumerate(range(0, len(x), seg)):
        sos = signal.butter(2, [f[i] / q, min(f[i] * q, SR / 2 - 100)], 'bandpass', fs=SR, output='sos')
        if zi is None: zi = np.zeros((sos.shape[0], 2))
        out[s:s + seg], zi = signal.sosfilt(sos, x[s:s + seg], zi=zi)
    return out
mix = np.zeros((N, 2))

# 1) original beach ambience for the first two seconds
src = os.path.join(WK, 'plate_audio.wav')
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', os.environ.get('SRC_VIDEO', os.path.join(SP, 'source.mov')),
                '-map', '0:a:0', '-ac', '2', '-ar', str(SR), src], check=True)
sr0, a0 = wavfile.read(src); a0 = a0.astype(np.float64) / 32768.0
n0 = min(len(a0), int(2.6 * SR)); g0 = env([(0, 1), (1.6, 1), (2.6, 0)])[:n0, None]
mix[:n0] += a0[:n0] * g0 * 0.9

# 2) wind + sand hiss building into the storm
gust = 0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t + 1) * np.sin(2 * np.pi * 0.23 * t)
wind = sweep_bp(noise(), 180, 900, 1.8) * env([(0, 0), (0.8, 0.15), (2.5, 0.6), (3.8, 1.0), (4.8, 0.7), (6.0, 0.35), (7.5, 0.12), (10, 0.05)]) * gust
mix += np.stack([wind, np.roll(wind, 900)], 1) * 0.55
hiss = hp(noise(), 3500) * env([(0, 0), (1.0, 0.05), (3.0, 0.35), (4.0, 0.45), (5.0, 0.2), (6.5, 0.06), (10, 0)])
mix += np.stack([hiss, hp(noise(), 3500) * env([(0, 0), (1.0, 0.05), (3.0, 0.35), (4.0, 0.45), (5.0, 0.2), (6.5, 0.06), (10, 0)])], 1) * 0.25
# 3) dust wall rumble, impact as it swallows the camera (~3.9 s)
rum = lp(noise(), 70, 4) * 6 + 0.4 * np.sin(2 * np.pi * 38 * t + 2 * np.sin(2 * np.pi * 0.5 * t))
rum *= env([(0, 0), (1.0, 0.05), (3.0, 0.5), (3.9, 1.0), (4.6, 0.4), (6.0, 0.15), (10, 0.05)])
mix += pan(rum, 0) * 0.8
# 4) organ drone: the space reveal (Interstellar-style pipe organ, A minor)
def organ(freq, start, att, amp):
    o = np.zeros(N); ph = rng.uniform(0, 6.28)
    for h, w in ((1, 1.0), (2, 0.55), (3, 0.32), (4, 0.25), (6, 0.12), (8, 0.08)):
        for det in (-0.6, 0.6):
            o += w * np.sin(2 * np.pi * (freq * h + det) * t + ph * h)
    trem = 1 + 0.06 * np.sin(2 * np.pi * 4.8 * t)
    e = np.clip((t - start) / att, 0, 1) ** 1.5
    return o * e * trem * amp
notes = [(55.0, 4.0, 2.2, 0.10), (82.41, 4.3, 2.0, 0.07), (110.0, 4.6, 2.0, 0.07), (130.81, 5.4, 1.8, 0.05), (164.81, 6.2, 1.8, 0.045), (220.0, 7.6, 1.2, 0.04), (261.63, 8.4, 1.0, 0.035)]
org = sum(organ(*n) for n in notes)
org *= env([(0, 1), (8.9, 1), (10, 0.55)])
org = lp(org, 2600)
mix += np.stack([org, np.roll(org, 240)], 1) * 0.55
# 5) ship flyby: doppler whoosh + sonic boom at frame 152 (5.07 s)
fb = np.zeros(N); s0, s1 = int(4.45 * SR), int(5.9 * SR)
seg = noise(s1 - s0)
fb[s0:s1] = sweep_bp(seg, 2600, 300, 2.5) * np.hanning(s1 - s0) ** 0.6
tone = np.zeros(N); tt = t[s0:s1] - 4.45
fr = 420 * np.exp(-tt * 1.6) + 90
tone[s0:s1] = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.hanning(s1 - s0) * 0.3
pan_l = np.clip((t - 4.6) / 0.9, -1, 1)
flyby = fb * 1.4 + tone
mix += np.stack([flyby * np.sqrt(0.5 * (1 - pan_l)), flyby * np.sqrt(0.5 * (1 + pan_l))], 1)
boom = np.zeros(N); b0 = int(5.07 * SR); bl = int(1.6 * SR)
bt = np.arange(bl) / SR
boom[b0:b0 + bl] = (lp(noise(bl), 140, 4) * 9 * np.exp(-bt * 3.0) + np.sin(2 * np.pi * 42 * bt) * np.exp(-bt * 4) * 0.9
                    + hp(noise(bl), 1500) * np.exp(-bt * 30) * 0.6)
mix += pan(boom, 0) * 0.9
# 6) surge: water roar + impact splash (~6.3 s), level rising
roar = lp(hp(noise(), 120), 1800) * env([(0, 0), (5.5, 0), (6.1, 0.8), (6.5, 1.0), (7.5, 0.5), (8.4, 0.25), (10, 0.12)])
mix += np.stack([roar, lp(hp(noise(), 120), 1800) * env([(0, 0), (5.5, 0), (6.1, 0.8), (6.5, 1.0), (7.5, 0.5), (8.4, 0.25), (10, 0.12)])], 1) * 0.5
def splash(at, size):
    s = np.zeros(N); a = int(at * SR); l = int(1.2 * SR); st = np.arange(l) / SR
    s[a:a + l] = (bp(noise(l), 300, 6000) * np.exp(-st * 5) * size + lp(noise(l), 200) * 3 * np.exp(-st * 6) * size)
    return s
mix += pan(splash(6.25, 1.0), -0.3) * 0.7 + pan(splash(6.35, 1.2), 0.15) * 0.7
mix += pan(splash(8.7, 1.5), 0.1) * 0.8
# 7) bubbles as the subject goes under
bub = np.zeros(N)
for i in range(26):
    at = 8.75 + rng.uniform(0, 0.9); l = int(rng.uniform(0.04, 0.1) * SR); a = int(at * SR)
    if a + l >= N: continue
    bt = np.arange(l) / SR; f0 = rng.uniform(300, 900)
    bub[a:a + l] += np.sin(2 * np.pi * (f0 * bt + 900 * bt * bt)) * np.exp(-bt * 40) * rng.uniform(0.2, 0.5)
mix += pan(bub, 0.05) * 0.6
# master: soft limiter, fade out
mix *= env([(0, 1), (9.6, 1), (10, 0)])[:, None]
peak = np.max(np.abs(mix)); mix = np.tanh(mix / peak * 1.6) * 0.89
wavfile.write(os.path.join(WK, 'soundtrack.wav'), SR, (mix * 32767).astype(np.int16))
print('soundtrack written', mix.shape)
