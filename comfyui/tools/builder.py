"""Tiny graph DSL -> real ComfyUI frontend -> canonical UI-format workflow JSON.

Nodes are created with LiteGraph.createNode inside the running frontend so widget
order, dynamic-combo children and widget-input sockets are exactly what ComfyUI
itself would save.
"""
import json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8188"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

C = {  # node colours (color, bgcolor)
    "input": ("#07599B", "#042C50"),
    "param": ("#956500", "#493200"),
    "model": ("#5E258B", "#2D1245"),
    "gen": ("#9A1F50", "#4A0F27"),
    "guide": ("#6B4500", "#2A1B00"),
    "post": ("#006F89", "#003A49"),
    "color": ("#007A60", "#003D30"),
    "out": ("#287A32", "#123C18"),
    "note": ("#6B4500", "#2A1B00"),
}


class Ref:
    def __init__(self, key, slot):
        self.key, self.slot = key, slot


class N:
    def __init__(self, g, key):
        self.g, self.key = g, key

    def __getitem__(self, slot):
        return Ref(self.key, slot)

    def to(self, dst, inp, slot=0):
        self.g.link(self[slot], dst, inp)
        return self


class G:
    def __init__(self):
        self.nodes, self.links, self.groups = [], [], []

    def node(self, type_, title=None, pos=(0, 0), widgets=None, kind=None, mode=0, size=None, collapsed=False, props=None):
        key = f"n{len(self.nodes)}"
        col = C.get(kind) if kind else None
        self.nodes.append(dict(key=key, type=type_, title=title, pos=list(pos), widgets=widgets or {},
                               color=col[0] if col else None, bgcolor=col[1] if col else None,
                               mode=mode, size=size, collapsed=collapsed, props=props or {}))
        return N(self, key)

    def note(self, title, text, pos, size=(520, 360)):
        return self.node("MarkdownNote", title, pos, {"text": text}, kind="note", size=size)

    def link(self, src, dst, inp):
        if isinstance(src, N):
            src = src[0]
        self.links.append([src.key, src.slot, dst.key, inp])

    def group(self, title, bounding, color="#3f789e"):
        self.groups.append(dict(title=title, bounding=list(bounding), color=color))


JS = r"""
async (spec) => {
  const app = window.app;
  const graph = app.graph;
  graph.clear();
  const byKey = {};
  const problems = [];
  for (const s of spec.nodes) {
    const n = LiteGraph.createNode(s.type);
    if (!n) { problems.push('unknown node type ' + s.type); continue; }
    graph.add(n);
    byKey[s.key] = n;
    if (s.title) n.title = s.title;
    n.pos = s.pos;
    if (s.color) { n.color = s.color; n.bgcolor = s.bgcolor; }
    if (s.mode) n.mode = s.mode;
    if (s.collapsed) n.flags = {...(n.flags||{}), collapsed: true};
    for (const [k, v] of Object.entries(s.props)) n.properties[k] = v;
    // set widgets in declared order so dynamic-combo parents spawn children first
    for (const [k, v] of Object.entries(s.widgets)) {
      const w = (n.widgets || []).find(w => w.name === k);
      if (!w) { problems.push(`${s.type}(${s.title}): no widget '${k}' have [${(n.widgets||[]).map(w=>w.name)}]`); continue; }
      w.value = v;
      try { w.callback && w.callback(v, app.canvas, n); } catch (e) {}
    }
    if (s.size) n.size = s.size; else { const sz = n.computeSize(); n.size = [Math.max(sz[0], 260), sz[1]]; }
  }
  for (const [a, ao, b, bi] of spec.links) {
    const A = byKey[a], B = byKey[b];
    if (!A || !B) { problems.push('link to missing node ' + a + '->' + b); continue; }
    const oi = typeof ao === 'number' ? ao : A.outputs.findIndex(o => o.name === ao || o.label === ao);
    const ii = typeof bi === 'number' ? bi : B.inputs.findIndex(i => i.name === bi);
    if (oi < 0 || ii < 0) { problems.push(`bad slot ${A.type}.${ao}(${oi}) -> ${B.type}.${bi}(${ii}) inputs=[${B.inputs.map(i=>i.name)}] outputs=[${A.outputs.map(o=>o.name)}]`); continue; }
    const l = A.connect(oi, B, ii);
    if (!l) problems.push(`connect failed ${A.type}.${ao} -> ${B.type}.${bi}`);
  }
  for (const gr of spec.groups) {
    const g = new LiteGraph.LGraphGroup(gr.title);
    g.pos = [gr.bounding[0], gr.bounding[1]]; g.size = [gr.bounding[2], gr.bounding[3]];
    g.color = gr.color; graph.add(g);
  }
  // widget values that were re-validated by connect() etc: re-apply
  for (const s of spec.nodes) {
    const n = byKey[s.key]; if (!n) continue;
    for (const [k, v] of Object.entries(s.widgets)) {
      const w = (n.widgets || []).find(w => w.name === k); if (w) w.value = v;
    }
  }
  const data = graph.serialize();
  return {data, problems};
}
"""


def build(g, out_path, extra=None):
    spec = dict(nodes=g.nodes, links=g.links, groups=g.groups)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = b.new_page()
        page.goto(URL)
        page.wait_for_function("window.app && window.app.graph && window.LiteGraph", timeout=120000)
        page.wait_for_timeout(2500)
        res = page.evaluate(JS, spec)
        b.close()
    if res["problems"]:
        raise SystemExit("BUILD PROBLEMS:\n  " + "\n  ".join(res["problems"]))
    data = res["data"]
    if extra:
        data.setdefault("extra", {}).update(extra)
    json.dump(data, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("wrote", out_path, len(data["nodes"]), "nodes", len(data["links"]), "links")
    return data
