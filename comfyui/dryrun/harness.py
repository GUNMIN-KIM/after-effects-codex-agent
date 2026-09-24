import json, copy, subprocess, time, uuid, urllib.request, urllib.error, os, sys, glob
import av, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
COMFY = os.environ.get("COMFY_DIR", os.path.join(HERE, "ComfyUI"))
OUT = os.path.join(COMFY, "output")
LOG = os.environ.get("COMFY_LOG", os.path.join(HERE, "server.log"))
WORKFLOWS = os.path.join(HERE, "..", "workflows")
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}

def sg_defs(wf):
    return {s["id"]: s for s in wf.get("definitions", {}).get("subgraphs", [])}

def set_widgets(wf, node_id, values):
    """values: {name: value}. Works for plain nodes (via widgets_values_named order) and subgraph instances."""
    n = next(n for n in wf["nodes"] if n["id"] == node_id)
    defs = sg_defs(wf)
    if n["type"] in defs:
        names = [i["name"] for i in defs[n["type"]]["inputs"] if i["type"] in WIDGET_TYPES]
    else:
        names = list(n.get("widgets_values_named", {}).keys())
    wv = n["widgets_values"]
    for k, v in values.items():
        idx = names.index(k)
        wv[idx] = v
        if "widgets_values_named" in n:
            n["widgets_values_named"][k] = v
    return wf

def http(path, data=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def to_api(wf, tag):
    runs = os.path.join(HERE, "runs"); os.makedirs(runs, exist_ok=True); p = f"{runs}/{tag}.wf.json"
    json.dump(wf, open(p, "w"), ensure_ascii=False)
    env = dict(os.environ, NODE_PATH=subprocess.check_output(["npm", "root", "-g"]).decode().strip())
    r = subprocess.run(["node", os.path.join(HERE, "to_api.js"), p, f"{runs}/{tag}.api.json"], capture_output=True, text=True, env=env, timeout=240)
    res = json.load(open(f"{runs}/{tag}.api.json"))
    if res.get("error") or res.get("dialogs"):
        print("FRONTEND:", res.get("error"), res.get("dialogs"))
    return res

def run(wf, tag, timeout=900):
    res = to_api(wf, tag)
    before = set(glob.glob(f"{OUT}/**/*.*", recursive=True))
    try:
        q = http("/prompt", {"prompt": res["output"], "client_id": "dryrun"})
    except urllib.error.HTTPError as e:
        body = json.loads(e.read()); print("VALIDATION FAILED", json.dumps(body, ensure_ascii=False)[:3000]); return None
    pid = q["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = http(f"/history/{pid}")
        if pid in h and h[pid].get("status", {}).get("completed") is not None:
            st = h[pid]["status"]
            if st.get("status_str") != "success":
                for m in st.get("messages", []):
                    if m[0] == "execution_error": print("EXEC ERROR", json.dumps(m[1], ensure_ascii=False)[:2500])
                return None
            break
        time.sleep(1)
    else:
        print("TIMEOUT"); return None
    after = sorted(set(glob.glob(f"{OUT}/**/*.*", recursive=True)) - before)
    return {"files": after, "secs": round(time.time() - t0, 1), "api": res["output"]}

def code_at(img, fx=1/6, fy=0.5):
    h, w, _ = img.shape
    y, x = int(h * fy), int(w * fx)
    p = img[y-2:y+3, x-2:x+3].reshape(-1, 3).mean(0) / 255.0
    return int(round(p[0] * 15)) + 16 * int(round(p[1] * 15)), p

def probe(path, fx=1/6):
    c = av.open(path)
    vs = c.streams.video[0]
    info = {"file": os.path.basename(path), "fps": float(vs.average_rate), "w": vs.codec_context.width, "h": vs.codec_context.height,
            "audio": any(s.type == "audio" for s in c.streams)}
    codes, frames = [], []
    for f in c.decode(video=0):
        a = f.to_ndarray(format="rgb24"); frames.append(a); codes.append(code_at(a, fx)[0])
    info["frames"] = len(frames)
    if info["audio"]:
        c2 = av.open(path); a = c2.streams.audio[0]
        info["audio_sec"] = round(float(a.duration * a.time_base), 3) if a.duration else None
    info["video_sec"] = round(len(frames) / info["fps"], 3)
    c.close()
    return info, codes, frames
