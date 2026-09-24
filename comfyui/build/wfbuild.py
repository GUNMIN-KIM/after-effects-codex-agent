"""Minimal LiteGraph/ComfyUI workflow builder driven by /object_info schemas.

Produces frontend-format workflows (top graph + subgraph definitions) with the same
conventions as the hand-built Creator UI files: linked widget inputs carry
{"widget": {"name": ...}}, subgraph widget inputs are promoted onto the instance,
and every node also carries widgets_values_named.
"""
import json
import uuid

OI = json.load(open(__file__.rsplit("/", 1)[0] + "/object_info_v0.31.1.json"))  # trimmed /object_info of ComfyUI v0.31.1
NS = uuid.UUID("6f1c2a52-3b7e-4f0e-9a51-0c0ffee0a2d1")  # stable ids -> clean git diffs


def sid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))
WIDGET = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}

COLORS = {
    "input": ("#07599B", "#042C50"),
    "control": ("#956500", "#493200"),
    "model": ("#5E258B", "#2D1245"),
    "gen": ("#9A1F50", "#4A0F27"),
    "video": ("#006F89", "#003A49"),
    "mask": ("#007A60", "#003D30"),
    "output": ("#287A32", "#123C18"),
    "note": ("#6B4500", "#2A1B00"),
    "sampling": ("#414B8F", "#202647"),
}

SEED_CONTROL = {"KSampler": "seed", "SamplerCustom": "noise_seed", "PrimitiveInt": "value"}


def _is_widget(spec):
    t = spec[0]
    if isinstance(t, list):
        return True
    if t in WIDGET:
        return not (len(spec) > 1 and isinstance(spec[1], dict) and spec[1].get("forceInput"))
    return False


def schema(ntype):
    info = OI[ntype]
    ins = []  # (name, type, is_widget, optional)
    for sect in ("required", "optional"):
        for name, spec in info["input"].get(sect, {}).items():
            t = spec[0]
            if t == "COMFY_DYNAMICCOMBO_V3":
                ins.append((name, "COMBO", True, sect == "optional"))
                opt = spec[1]["options"][0]  # builder only uses the first option ("scale dimensions")
                for sub, sspec in opt["inputs"]["required"].items():
                    ins.append((f"{name}.{sub}", "COMBO" if isinstance(sspec[0], list) else sspec[0], True, False))
                continue
            if t == "COMFY_AUTOGROW_V3":
                continue  # handled explicitly (values.a, values.b ...)
            if t == "COMFY_MATCHTYPE_V3":
                ins.append((name, "*", False, sect == "optional"))
                continue
            if isinstance(t, list):
                t = "COMBO"
            ins.append((name, t, _is_widget(spec), sect == "optional"))
            if ntype in SEED_CONTROL and SEED_CONTROL[ntype] == name:
                ins.append(("control_after_generate", "COMBO", True, False))
            if name == "image" and ntype == "LoadImage":
                ins.append(("upload", "IMAGE_UPLOAD", True, False))
            if name == "file" and ntype == "LoadVideo":
                ins.append(("upload", "IMAGE_UPLOAD", True, False))
    outs = [(n, t if not isinstance(t, list) else "COMBO") for n, t in zip(info.get("output_name") or info["output"], info["output"])]
    return ins, outs


class Graph:
    def __init__(self, ids):
        self.ids = ids  # shared counters {"node": n, "link": n}
        self.nodes = []
        self.links = []  # dicts
        self.groups = []
        self.byid = {}

    def _nid(self):
        self.ids["node"] += 1
        return self.ids["node"]

    def _lid(self):
        self.ids["link"] += 1
        return self.ids["link"]

    def add(self, ntype, title=None, pos=(0, 0), size=(300, 120), widgets=None, color=None, mode=0, n_values=0,
            match_type=None, out_types=None, properties=None, nid=None):
        widgets = widgets or {}
        node = {"id": nid or self._nid(), "type": ntype, "pos": list(pos), "size": list(size), "flags": {}, "order": 0, "mode": mode,
                "inputs": [], "outputs": [], "properties": {"Node name for S&R": ntype}}
        if properties:
            node["properties"].update(properties)
        if title:
            node["title"] = title
        wnames, wvals = [], []
        if ntype in OI:
            ins, outs = schema(ntype)
            for name, t, is_w, optional in ins:
                if is_w:
                    wnames.append(name)
                    wvals.append(widgets[name] if name in widgets else _default(ntype, name))
                else:
                    slot = {"localized_name": name, "name": name, "type": match_type if t == "*" else t, "link": None}
                    if optional:
                        slot["shape"] = 7
                    node["inputs"].append(slot)
            if ntype == "ComfyMathExpression":
                for k in "abcdefghijklmnopqrstuvwxyz"[:max(1, n_values)]:
                    slot = {"label": k, "localized_name": f"values.{k}", "name": f"values.{k}", "type": "FLOAT,INT,BOOLEAN", "link": None}
                    if k != "a":
                        slot["shape"] = 7
                    node["inputs"].append(slot)
            for i, (name, t) in enumerate(outs):
                node["outputs"].append({"localized_name": name, "name": name, "type": (match_type if t == "*" else t), "links": []})
            if out_types:
                for o, t in zip(node["outputs"], out_types):
                    o["type"] = t
        unknown = set(widgets) - set(wnames)
        assert not unknown, f"{ntype}: unknown widgets {unknown}"
        if wnames:
            node["widgets_values"] = [v for n, v in zip(wnames, wvals) if n != "upload" or True]
            node["widgets_values_named"] = dict(zip(wnames, wvals))
        if color:
            node["color"], node["bgcolor"] = COLORS[color]
        self.nodes.append(node)
        self.byid[node["id"]] = node
        return node

    def _in_slot(self, node, name):
        for i, s in enumerate(node["inputs"]):
            if s["name"] == name:
                return i
        # widget converted to input
        wt = None
        if node["type"] in OI:
            for n, t, is_w, _ in schema(node["type"])[0]:
                if n == name:
                    wt = t
        assert wt is not None, f"{node['type']} has no input {name}"
        node["inputs"].append({"localized_name": name.split(".")[-1], "name": name, "type": wt, "widget": {"name": name}, "link": None})
        return len(node["inputs"]) - 1

    def _out_slot(self, node, out):
        if isinstance(out, int):
            return out
        for i, s in enumerate(node["outputs"]):
            if s["name"] == out:
                return i
        raise KeyError(f"{node['type']} has no output {out}")

    def link(self, src, out, dst, inp):
        """src/dst: node dicts; out: output name/index; inp: input name."""
        oi = self._out_slot(src, out)
        ii = self._in_slot(dst, inp)
        t = src["outputs"][oi]["type"]
        lid = self._lid()
        assert dst["inputs"][ii]["link"] is None, f"input {inp} of {dst['id']} already linked"
        dst["inputs"][ii]["link"] = lid
        src["outputs"][oi]["links"].append(lid)
        self.links.append({"id": lid, "origin_id": src["id"], "origin_slot": oi, "target_id": dst["id"], "target_slot": ii, "type": t})
        return lid

    def group(self, title, nodes, color="#48538E", pad=40):
        xs = [n["pos"][0] for n in nodes]
        ys = [n["pos"][1] for n in nodes]
        xe = [n["pos"][0] + n["size"][0] for n in nodes]
        ye = [n["pos"][1] + n["size"][1] for n in nodes]
        self.groups.append({"id": len(self.groups) + 1, "title": title,
                            "bounding": [min(xs) - pad, min(ys) - pad - 40, max(xe) - min(xs) + 2 * pad, max(ye) - min(ys) + 2 * pad + 40],
                            "color": color, "flags": {}})


def _default(ntype, name):
    if name == "control_after_generate":
        return "fixed"
    if name == "upload":
        return "image"
    info = OI[ntype]["input"]
    for sect in ("required", "optional"):
        spec = info.get(sect, {}).get(name)
        if spec is not None:
            if isinstance(spec[0], list):
                return spec[0][0] if spec[0] else None
            opts = spec[1] if len(spec) > 1 else {}
            if "default" in opts:
                return opts["default"]
            if spec[0] == "COMBO":
                return (opts.get("options") or [None])[0]
            return {"INT": 0, "FLOAT": 0.0, "STRING": "", "BOOLEAN": False}.get(spec[0])
    if "." in name:
        base, sub = name.split(".", 1)
        spec = info["required"][base]
        opt = spec[1]["options"][0]["inputs"]["required"][sub]
        return opt[1].get("default") if len(opt) > 1 else None
    return None


class Subgraph(Graph):
    def __init__(self, ids, name, description=""):
        super().__init__(ids)
        self.sid = sid("subgraph", name)
        self.name = name
        self.description = description
        self.inputs = []   # {"name","type","label","linkIds","default","widget"}
        self.outputs = []
        self.IN = {"id": -10, "outputs": None}
        self.OUT = {"id": -20}

    def add_input(self, name, typ, label, default=None):
        self.inputs.append({"id": sid(self.name, "in", name), "name": name, "type": typ, "linkIds": [], "localized_name": name,
                            "label": label, "_default": default})
        return len(self.inputs) - 1

    def add_output(self, name, typ, label=None):
        self.outputs.append({"id": sid(self.name, "out", name), "name": name, "type": typ, "linkIds": [], "localized_name": name,
                             **({"label": label} if label else {})})
        return len(self.outputs) - 1

    def from_input(self, name, dst, inp):
        idx = next(i for i, s in enumerate(self.inputs) if s["name"] == name)
        ii = self._in_slot(dst, inp)
        lid = self._lid()
        dst["inputs"][ii]["link"] = lid
        self.inputs[idx]["linkIds"].append(lid)
        self.links.append({"id": lid, "origin_id": -10, "origin_slot": idx, "target_id": dst["id"], "target_slot": ii,
                           "type": self.inputs[idx]["type"]})
        return lid

    def to_output(self, name, src, out):
        idx = next(i for i, s in enumerate(self.outputs) if s["name"] == name)
        oi = self._out_slot(src, out)
        lid = self._lid()
        src["outputs"][oi]["links"].append(lid)
        self.outputs[idx]["linkIds"].append(lid)
        self.links.append({"id": lid, "origin_id": src["id"], "origin_slot": oi, "target_id": -20, "target_slot": idx,
                           "type": self.outputs[idx]["type"]})
        return lid

    def definition(self):
        xs = [n["pos"][0] for n in self.nodes]
        ys = [n["pos"][1] for n in self.nodes]
        xe = [n["pos"][0] + n["size"][0] for n in self.nodes]
        h_in = 40 + 20 * len(self.inputs)
        ins = []
        for i, s in enumerate(self.inputs):
            d = {k: v for k, v in s.items() if not k.startswith("_")}
            d["pos"] = [min(xs) - 300, min(ys) + 24 + 20 * i]
            ins.append(d)
        outs = []
        for i, s in enumerate(self.outputs):
            d = dict(s)
            d["pos"] = [max(xe) + 220, min(ys) + 24 + 20 * i]
            outs.append(d)
        return {
            "id": self.sid, "version": 1,
            "state": {"lastGroupId": len(self.groups), "lastNodeId": self.ids["node"], "lastLinkId": self.ids["link"], "lastRerouteId": 0},
            "revision": 0, "config": {}, "name": self.name, "description": self.description,
            "inputNode": {"id": -10, "bounding": [min(xs) - 400, min(ys), 380, h_in]},
            "outputNode": {"id": -20, "bounding": [max(xe) + 200, min(ys), 160, 40 + 20 * len(self.outputs)]},
            "inputs": ins, "outputs": outs, "widgets": [], "nodes": self.nodes, "groups": self.groups, "links": self.links,
            "extra": {"workflowRendererVersion": "LG"},
        }

    def instance(self, g, title, pos, size, color="gen"):
        """Create the subgraph node on parent graph g; promoted widget values come from input defaults."""
        node = {"id": g._nid(), "type": self.sid, "pos": list(pos), "size": list(size), "flags": {}, "order": 0, "mode": 0,
                "inputs": [], "outputs": [], "title": title, "properties": {"previewExposures": []}}
        wv, named = [], {}
        for s in self.inputs:
            slot = {"label": s["label"], "name": s["name"], "type": s["type"], "link": None}
            if s["type"] in WIDGET:
                slot["widget"] = {"name": s["name"]}
                wv.append(s["_default"])
                named[s["name"]] = s["_default"]
            elif s["type"] == "IMAGE" and s["name"] == "reference_image":
                slot["shape"] = 7
            node["inputs"].append(slot)
        for s in self.outputs:
            node["outputs"].append({"name": s["name"], "type": s["type"], "links": [], **({"label": s["label"]} if "label" in s else {})})
        node["widgets_values"] = wv
        node["widgets_values_named"] = named
        node["color"], node["bgcolor"] = COLORS[color]
        g.nodes.append(node)
        g.byid[node["id"]] = node
        return node


def top_links(g):
    return [[l["id"], l["origin_id"], l["origin_slot"], l["target_id"], l["target_slot"], l["type"]] for l in g.links]
