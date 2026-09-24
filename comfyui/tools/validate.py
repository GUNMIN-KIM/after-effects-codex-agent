"""Load ComfyUI UI-format workflows in the real frontend, convert with graphToPrompt,
and submit to /prompt so the backend validates every node/input/combo value.

usage: python validate.py wf1.json [wf2.json ...]
"""
import json, sys, copy, time, urllib.request
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8188"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def patch_media(wf):
    """Point file inputs at the local test media so validation can resolve them."""
    wf = copy.deepcopy(wf)
    subs = (wf.get("definitions") or {}).get("subgraphs", [])
    nodes = list(wf["nodes"]) + [n for s in subs for n in s["nodes"]]
    for n in nodes:
        wv = n.get("widgets_values")
        if n["type"] == "VHS_LoadVideo" and isinstance(wv, dict):
            wv["video"] = "test.mp4"
            if isinstance(wv.get("videopreview"), dict):
                wv["videopreview"]["params"]["filename"] = "test.mp4"
        elif n["type"] == "LoadVideo" and isinstance(wv, list):
            wv[0] = "test.mp4"
        elif n["type"] == "LoadImage" and isinstance(wv, list):
            wv[0] = "test.png"
    return wf


def post(path, data=None):
    req = urllib.request.Request(URL + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main(paths):
    ok_all = True
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = b.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.goto(URL)
        page.wait_for_function("window.app && window.app.graph && window.LiteGraph", timeout=120000)
        time.sleep(3)
        for path in paths:
            logs.clear()
            wf = patch_media(json.load(open(path)))
            res = page.evaluate(
                """async (wf) => {
                    await window.app.loadGraphData(wf, true, true, 'validate');
                    const missing = [];
                    const walk = (g) => { for (const n of g.nodes || g._nodes || []) {
                        if (n.has_errors || (n.constructor && n.constructor.nodeData === undefined && !n.isSubgraphNode?.() && !['Note','MarkdownNote','Reroute','PrimitiveNode'].includes(n.type)))
                            missing.push(n.type + '#' + n.id);
                        if (n.subgraph) walk(n.subgraph);
                    } };
                    walk(window.app.graph);
                    const pr = await window.app.graphToPrompt();
                    return {missing, prompt: pr.output};
                }""",
                wf,
            )
            prompt = res["prompt"]
            status, body = post("/prompt", {"prompt": prompt, "client_id": "validator"})
            post("/interrupt", {})
            post("/queue", {"clear": True})
            errs = body.get("node_errors") or {}
            ok = status == 200 and not errs and not res["missing"]
            ok_all &= ok
            print(f"\n=== {path}\n  api nodes: {len(prompt)}  status: {status}  missing/err nodes: {res['missing']}")
            if body.get("error") and status != 200:
                print("  error:", json.dumps(body.get("error"), ensure_ascii=False)[:600])
            for nid, e in errs.items():
                print(f"  node {nid} ({e.get('class_type')}):")
                for x in e.get("errors", []):
                    print("     -", x.get("message"), "|", x.get("details"))
            for l in logs[:15]:
                if "favicon" not in l:
                    print("  console", l[:300])
            json.dump(prompt, open(path[:-5] + ".api.json", "w"), indent=1)
        b.close()
    print("\nALL OK" if ok_all else "\nFAILURES")
    return ok_all


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) else 1)
