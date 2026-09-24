"""Execute the model-free parts of a workflow for real: the VAE decode outputs are
replaced by stubs built from the source frames, everything downstream runs as-is."""
import json, sys, time, urllib.request, uuid

URL = "http://127.0.0.1:8188"


def post(path, data):
    req = urllib.request.Request(URL + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(path):
    with urllib.request.urlopen(URL + path) as r:
        return json.loads(r.read())


def find(p, cls, title_part=""):
    ids = [k for k, v in p.items() if v["class_type"] == cls and title_part in v.get("_meta", {}).get("title", "")]
    assert len(ids) >= 1, (cls, title_part)
    return ids


def run(p, label):
    pid = post("/prompt", {"prompt": p, "client_id": "rt"})
    print(label, "submit:", pid[0], json.dumps(pid[1].get("node_errors") or pid[1].get("error") or "", ensure_ascii=False)[:800])
    if pid[0] != 200:
        return False
    prompt_id = pid[1]["prompt_id"]
    for _ in range(600):
        h = get(f"/history/{prompt_id}")
        if prompt_id in h:
            st = h[prompt_id]["status"]
            print(label, "status:", st.get("status_str"))
            for m in st.get("messages", []):
                if m[0] in ("execution_error",):
                    d = m[1]
                    print("  ERROR in", d.get("node_id"), d.get("node_type"), d.get("exception_message", "")[:600])
            outs = h[prompt_id].get("outputs", {})
            for nid, o in outs.items():
                for k, v in o.items():
                    print("  out", nid, k, json.dumps(v, ensure_ascii=False)[:400])
            return st.get("status_str") == "success"
        time.sleep(1)
    print("timeout")
    return False
