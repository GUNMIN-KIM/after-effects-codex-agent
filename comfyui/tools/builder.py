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
        self.nodes, self.links, self.groups, self.subs, self.post_groups = [], [], [], [], []

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

    def group(self, title, bounding, color="#3f789e", main=False):
        (self.post_groups if main else self.groups).append(dict(title=title, bounding=list(bounding), color=color))

    def core(self, name, title, pos, main_nodes, relocate=None, color=None, size=None, out_labels=None):
        """Convert every node except `main_nodes` into one subgraph (after links are built).
        `relocate` maps main-graph nodes to new positions after conversion."""
        col = C.get(color) if color else None
        self.subs.append(dict(name=name, title=title, pos=list(pos), size=size,
                              main=[n if isinstance(n, str) else n.key for n in main_nodes],
                              relocate={n.key: list(p) for n, p in (relocate or {}).items()},
                              color=col[0] if col else None, bgcolor=col[1] if col else None,
                              out_labels=out_labels or {}))


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
  // ── subgraph conversion ──
  for (const sub of spec.subs || []) {
    const mainSet = new Set(sub.main);
    // order inner nodes by the earliest control-panel node feeding them → subgraph inputs follow panel order
    const idx = {}; spec.nodes.forEach((s, i) => idx[s.key] = i);
    const firstSrc = {};
    for (const [a, ao, b, bi] of spec.links) if (mainSet.has(a) && !mainSet.has(b)) firstSrc[b] = Math.min(firstSrc[b] ?? 1e9, idx[a]);
    const inner = spec.nodes.filter(s => !mainSet.has(s.key) && byKey[s.key]);
    inner.sort((x, y) => ((firstSrc[x.key] ?? 1e9) - (firstSrc[y.key] ?? 1e9)) || (idx[x.key] - idx[y.key]));
    const items = new Set();
    for (const s of inner) items.add(byKey[s.key]);
    for (const gr of graph._groups || graph.groups || []) items.add(gr);
    const res = graph.convertToSubgraph(items);
    const node = res.node, sg = res.subgraph;
    node.title = sub.title; sg.name = sub.name;
    node.pos = sub.pos;
    if (sub.color) { node.color = sub.color; node.bgcolor = sub.bgcolor; }
    // name subgraph inputs after the main-graph control that feeds them
    node.inputs.forEach((inp, i) => {
      try {
        const l = graph.links instanceof Map ? graph.links.get(inp.link) : graph.links[inp.link];
        const src = l && graph.getNodeById(l.origin_id);
        if (!src) return;
        let label = (src.title || src.type).split(' (')[0].trim();
        const oname = src.outputs[l.origin_slot]?.name;
        if (src.outputs.length > 1 && oname) label = `${label} · ${oname}`;
        inp.label = label;
        if (sg.inputs[i]) sg.inputs[i].label = label;
      } catch (e) { problems.push('label in ' + e); }
    });
    node.outputs.forEach((out, j) => {
      try {
        const so = sg.outputs[j];
        const lid = so.linkIds && so.linkIds[0];
        const l = lid !== undefined ? (sg.links instanceof Map ? sg.links.get(lid) : sg.links[lid]) : null;
        const src = l && sg.getNodeById(l.origin_id);
        if (!src) return;
        let label = (src.title || src.type);
        label = (sub.out_labels && sub.out_labels[label]) || label.split(' (')[0].trim();
        out.label = label; so.label = label;
      } catch (e) { problems.push('label out ' + e); }
    });
    for (const [k, p] of Object.entries(sub.relocate)) if (byKey[k]) byKey[k].pos = p;
    if (sub.size) node.size = sub.size; else { const sz = node.computeSize(); node.size = [Math.max(sz[0], 520), sz[1]]; }
    sub.__inputs = node.inputs.length;
  }
  for (const gr of spec.post_groups || []) {
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


def _strip_nulls(o, key=None):
    """Drop dict keys whose value is None (the frontend's serialize() emits e.g.
    floatingLinks: null, which its own loader then fails on). Keep link fields and widget values."""
    if key in ("widgets_values", "widgets_values_named"):
        return o
    if isinstance(o, dict):
        return {k: _strip_nulls(v, k) for k, v in o.items() if v is not None or k in ("link", "links")}
    if isinstance(o, list):
        return [_strip_nulls(v) for v in o]
    return o


def _fix_autogrow_slots(data):
    """convertToSubgraph serialises ComfyMathExpression inputs as [a, b, expression, c, ...]
    while numbering link target slots as [a, b, c, ..., expression]. Reorder the inputs to match
    the link numbering and re-derive every input's link id from the subgraph link table."""
    for sg in (data.get("definitions") or {}).get("subgraphs", []):
        by_target = {}
        for l in sg.get("links", []):
            by_target[(l["target_id"], l["target_slot"])] = l["id"]
        for n in sg["nodes"]:
            if n["type"] != "ComfyMathExpression":
                continue
            ins = n.get("inputs", [])
            vals = sorted([i for i in ins if i["name"].startswith("values.")], key=lambda i: i["name"])
            rest = [i for i in ins if not i["name"].startswith("values.")]
            n["inputs"] = vals + rest
            for idx, i in enumerate(n["inputs"]):
                i["link"] = by_target.get((n["id"], idx))
    return data


def build(g, out_path, extra=None):
    links = g.links
    spec = dict(nodes=g.nodes, links=links, groups=g.groups, subs=g.subs, post_groups=g.post_groups)
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
    data = _fix_autogrow_slots(_strip_nulls(res["data"]))
    if extra:
        data.setdefault("extra", {}).update(extra)
    json.dump(data, open(out_path, "w"), ensure_ascii=False, indent=2)
    print("wrote", out_path, len(data["nodes"]), "nodes", len(data["links"]), "links")
    return data
