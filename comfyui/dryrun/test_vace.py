import json, copy, sys, re
import numpy as np
from PIL import Image
from harness import *

def src_frames(path):
    c = av.open(path); fr = [f.to_ndarray(format="rgb24") for f in c.decode(video=0)]; c.close(); return fr

def disc(i, n, w, h):
    return w * (0.55 + 0.3 * i / max(1, n - 1)), h * 0.5, min(w, h) * 0.18

def mk(wf_path, src, mask, ref=True, **ctrl):
    wf = json.load(open(wf_path))
    mc = next(n for n in wf["nodes"] if n.get("title", "").startswith("4. MAIN CONTROL"))
    for n in wf["nodes"]:
        t = n.get("title", "")
        if t.startswith("1. Source"): n["widgets_values"][0] = src; n["widgets_values_named"]["file"] = src
        if t.startswith("2. Mask"): n["widgets_values"][0] = mask; n["widgets_values_named"]["file"] = mask
        if t.startswith("3. Reference"):
            n["widgets_values"][0] = "ref_portrait.png"; n["widgets_values_named"]["image"] = "ref_portrait.png"
            if not ref: n["mode"] = 4
    set_widgets(wf, mc["id"], ctrl)
    return wf

def check(tag, r, src, mask, n_src, mask_n, exp_frames, exp_fps, exp_wh, lock=True, gray_inside=True):
    vids = [f for f in r["files"] if f.endswith(".mp4")]
    main = [f for f in vids if "_control" not in f and "_compare" not in f][0]
    ctrl = [f for f in vids if "_control" in f]
    info, codes, frames = probe(main)
    S = src_frames(os.path.join(COMFY, "input", src))
    w, h = info["w"], info["h"]
    errs = []
    if info["frames"] != exp_frames: errs.append(f"frames {info['frames']}!={exp_frames}")
    if abs(info["fps"] - exp_fps) > 0.01: errs.append(f"fps {info['fps']}!={exp_fps}")
    if (w, h) != exp_wh: errs.append(f"size {(w,h)}!={exp_wh}")
    if not info["audio"]: errs.append("no audio")
    bad = [i for i, c in enumerate(codes) if c != i]
    if bad: errs.append(f"index code mismatch at {bad[:5]}")
    # gray inside the (held) mask disc + pixel-lock diff outside
    grays, diffs = [], []
    yy, xx = np.mgrid[0:h, 0:w]
    for i in range(0, info["frames"], max(1, info["frames"] // 6)):
        mi = min(i, mask_n - 1)
        cx, cy, rr = disc(mi, mask_n, w, h)
        grays.append(frames[i][int(cy), int(cx)].astype(int).tolist())
        ref_img = np.asarray(Image.fromarray(S[i]).resize((w, h), Image.LANCZOS)).astype(float)
        far = ((xx - cx) ** 2 + (yy - cy) ** 2) > (rr * 1.6) ** 2
        diffs.append(float(np.abs(frames[i].astype(float) - ref_img)[far].mean()))
    g_ok = all(abs(v - 128) <= 6 for g in grays for v in g)
    if gray_inside and not g_ok: errs.append(f"mask centre not gray: {grays[:3]}")
    md = max(diffs)
    if lock and md > 2.0: errs.append(f"pixel-lock outside diff {md:.2f} > 2")
    cinfo = probe(ctrl[0])[0] if ctrl else None
    print(f"[{'PASS' if not errs else 'FAIL'}] {tag}: {info['frames']}f {info['fps']:.3f}fps {w}x{h} audio={info['audio']}({info.get('audio_sec')}s) "
          f"outside_diff_max={md:.2f} centre={grays[0]} ctrl={cinfo and (cinfo['frames'], cinfo['w'], cinfo['h'])} {r['secs']}s")
    for e in errs: print("      -", e)
    return not errs

def ks_log(n=1):
    lines = [l for l in open(LOG).read().splitlines() if "DRYRUN KSampler" in l]
    return lines[-n:]

if __name__ == "__main__":
    which = sys.argv[1:] or ["basic", "inpaint"]
    files = {"basic": os.path.join(WORKFLOWS, "WAN_VACE_1.3B_14B_CreatorUI.json"), "inpaint": os.path.join(WORKFLOWS, "WAN_VACE_Inpaint_2x_PixelLock_CreatorUI.json")}
    ok = True
    for k in which:
        f = files[k]; sc = 2 if k == "inpaint" else 1
        cases = [
            ("default_land", dict(src="src_land_50f_30.mp4", mask="mask_land_50f_30.mp4"), {}, (50, 30.0, (640*sc, 360*sc), 50)),
            ("short_mask_hold", dict(src="src_land_50f_30.mp4", mask="mask_land_40f_30.mp4"), {}, (50, 30.0, (640*sc, 360*sc), 40)),
            ("portrait_custom_len_1s", dict(src="src_port_33f_24.mp4", mask="mask_port_33f_24.mp4"),
             {"use_custom_duration": True, "duration_seconds": 1.0}, (24, 24.0, (360*sc, 640*sc), 33)),
            ("hd_2997_scale1_noref", dict(src="src_hd_17f_2997.mp4", mask="mask_hd_17f_2997.mp4", ref=False),
             {"output_scale": 1.0}, (17, 29.97, (1920, 1080), 17)),
            ("custom_res_keep_aspect", dict(src="src_land_50f_30.mp4", mask="mask_land_50f_30.mp4"),
             {"use_custom_resolution": True, "custom_width": 1001, "keep_aspect_ratio": True}, (50, 30.0, (1000, 564), 50)),
            ("custom_fps_20", dict(src="src_land_50f_30.mp4", mask="mask_land_50f_30.mp4"),
             {"use_custom_fps": True, "custom_fps": 20.0}, (50, 20.0, (640*sc, 360*sc), 50)),
        ]
        for tag, io_, ctrl, (ef, efps, ewh, mn) in cases:
            wf = mk(f, io_["src"], io_["mask"], io_.get("ref", True), **ctrl)
            r = run(wf, f"{k}_{tag}")
            if not r: print(f"[FAIL] {k}_{tag}: run failed"); ok = False; continue
            ok &= check(f"{k}_{tag}", r, io_["src"], io_["mask"], None, mn, ef, efps, ewh)
            print("      ", ks_log()[0].split("DRYRUN ")[1])
        # options: turbo off, 480p canvas, invert, expand, block align, pixel lock off
        wf = mk(f, "src_land_50f_30.mp4", "mask_land_50f_30.mp4", turbo=False, canvas_720p=False, invert_mask=True,
                mask_expand=6, mask_block_align=True, pixel_lock=False)
        r = run(wf, f"{k}_options")
        if not r: print(f"[FAIL] {k}_options: run failed"); ok = False
        else:
            info, codes, frames = probe([x for x in r["files"] if x.endswith('.mp4') and '_control' not in x and '_compare' not in x][0])
            ctrl_info, _, cframes = probe([x for x in r["files"] if '_control' in x][0])
            # inverted: disc keeps source, background becomes gray in control
            cx, cy, rr = disc(0, 50, ctrl_info["w"], ctrl_info["h"])
            print(f"[{'PASS' if info['frames']==50 else 'FAIL'}] {k}_options: {info['frames']}f {info['w']}x{info['h']} control {ctrl_info['w']}x{ctrl_info['h']} "
                  f"ctrl_bg={cframes[0][5,5].tolist()} ctrl_disc={cframes[0][int(cy),int(cx)].tolist()}")
            print("      ", ks_log()[0].split("DRYRUN ")[1])
    print("ALL PASS" if ok else "SOME FAILED")
