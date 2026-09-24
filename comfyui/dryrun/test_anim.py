import json, copy
from harness import *
SRC = json.load(open(os.path.join(WORKFLOWS, "WAN_Animate2_CreatorUI.json")))

def mk(vid, F=None, **ctrl):
    wf = copy.deepcopy(SRC)
    for n in wf["nodes"]:
        if n["type"] == "LoadVideo": n["widgets_values"][0] = vid; n["widgets_values_named"]["file"] = vid
        if n["type"] == "LoadImage": n["widgets_values"][0] = "ref_portrait.png"; n["widgets_values_named"]["image"] = "ref_portrait.png"
    set_widgets(wf, 638, ctrl)
    if F:
        sg = next(s for s in wf["definitions"]["subgraphs"] if s["name"] == "MAIN CONTROL")
        n = next(n for n in sg["nodes"] if n["id"] == 686); n["widgets_values"][0] = F
    return wf

def lastlog(k, n):
    return [l.split("DRYRUN ")[1] for l in open(LOG).read().splitlines() if f"DRYRUN {k}" in l][-n:]

cases = [
    ("source_100f", "drv_land_100f_25.mp4", {}, {}, 100, 25.0, (640, 360)),
    ("source_170f_3chunks", "drv_land_170f_30.mp4", {}, {}, 170, 30.0, (640, 360)),
    ("source_50f_portrait", "drv_port_50f_24.mp4", {}, {}, 50, 24.0, (360, 640)),
    ("distill_off", "drv_land_100f_25.mp4", {}, dict(use_distilled=False), 100, 25.0, (640, 360)),
    ("custom_len_3s", "drv_land_100f_25.mp4", {}, dict(use_custom_duration=True, duration_seconds=3.0), 75, 25.0, (640, 360)),
    ("custom_len_longer_than_src", "drv_land_100f_25.mp4", {}, dict(use_custom_duration=True, duration_seconds=6.0), 150, 25.0, (640, 360)),
    ("custom_len_over_cap", "drv_land_170f_30.mp4", {}, dict(use_custom_duration=True, duration_seconds=9.0), 241, 30.0, (640, 360)),
    ("custom_res_keep_aspect_odd", "drv_port_50f_24.mp4", {}, dict(use_custom_resolution=True, custom_width=1001, keep_aspect_ratio=True), 50, 24.0, (1000, 1780)),
    ("custom_res_free_odd", "drv_land_100f_25.mp4", {}, dict(use_custom_resolution=True, custom_width=853, custom_height=481, keep_aspect_ratio=False), 100, 25.0, (852, 480)),
    ("custom_fps_12", "drv_port_50f_24.mp4", {}, dict(use_custom_fps=True, custom_fps=12.0), 50, 12.0, (360, 640)),
    ("F49_170f", "drv_land_170f_30.mp4", {"F": 49}, {}, 145, 30.0, (640, 360)),
]
ok = True
for tag, vid, extra, ctrl, ef, efps, ewh in cases:
    r = run(mk(vid, **extra, **ctrl), f"anim_{tag}")
    if not r: print("[FAIL]", tag, "run failed"); ok = False; continue
    main = [f for f in r["files"] if f.endswith(".mp4") and "_compare" not in f][0]
    info, codes, _ = probe(main)
    n_src = int(vid.split("_")[2][:-1])
    exp_codes = [min(i, n_src - 1) for i in range(info["frames"])]
    bad = [i for i, (c, e) in enumerate(zip(codes, exp_codes)) if c != e]
    errs = []
    if info["frames"] != ef: errs.append(f"frames {info['frames']} != {ef}")
    if abs(info["fps"] - efps) > 0.01: errs.append(f"fps {info['fps']}")
    if (info["w"], info["h"]) != ewh: errs.append(f"size {(info['w'], info['h'])} != {ewh}")
    if bad: errs.append(f"pose order mismatch at {bad[:5]}")
    cmp = [f for f in r["files"] if "_compare" in f]
    cinfo, ccodes, _ = probe(cmp[0], fx=1/12)
    print(f"[{'PASS' if not errs else 'FAIL'}] {tag}: {info['frames']}f {info['fps']}fps {info['w']}x{info['h']} audio={info['audio']} | compare {cinfo['frames']}f {cinfo['w']}x{cinfo['h']} | {lastlog('SamplerCustom',1)[0]}")
    for e in errs: print("     -", e)
    ok &= not errs
print("ALL PASS" if ok else "SOME FAILED")
