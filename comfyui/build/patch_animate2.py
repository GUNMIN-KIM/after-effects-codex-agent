"""Develop the Wan Animate 2 Creator UI workflow (revision 3 -> 4) in place."""
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
NS = uuid.UUID("6f1c2a52-3b7e-4f0e-9a51-0c0ffee0a2d1")

wf = json.load(open(os.path.join(HERE, "..", "source", "WAN_Animate2_rev3_original.json")))
subs = {s["name"]: s for s in wf["definitions"]["subgraphs"]}
sg = subs["MAIN CONTROL"]
st = subs["Video Stitch"]
top = {n["id"]: n for n in wf["nodes"]}
inst = top[638]
inner = {n["id"]: n for n in sg["nodes"]}
links = {l["id"]: l for l in sg["links"]}
state = sg["state"]
WIDGET = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def nid():
    state["lastNodeId"] += 1
    return state["lastNodeId"]


def lid():
    state["lastLinkId"] += 1
    return state["lastLinkId"]


def add_link(o, os_, t, ts, typ):
    l = {"id": lid(), "origin_id": o, "origin_slot": os_, "target_id": t, "target_slot": ts, "type": typ}
    sg["links"].append(l)
    links[l["id"]] = l
    if o != -10:
        inner[o]["outputs"][os_]["links"].append(l["id"])
    inner[t]["inputs"][ts]["link"] = l["id"]
    return l


def math_node(expr, title, pos, color=("#956500", "#493200")):
    n = {"id": nid(), "type": "ComfyMathExpression", "pos": pos, "size": [420, 170], "flags": {}, "order": 0, "mode": 0,
         "inputs": [{"label": "a", "localized_name": "values.a", "name": "values.a", "type": "FLOAT,INT,BOOLEAN", "link": None},
                    {"label": "b", "localized_name": "values.b", "name": "values.b", "shape": 7, "type": "FLOAT,INT,BOOLEAN", "link": None}],
         "outputs": [{"localized_name": "FLOAT", "name": "FLOAT", "type": "FLOAT", "links": []},
                     {"localized_name": "INT", "name": "INT", "type": "INT", "links": []},
                     {"localized_name": "BOOL", "name": "BOOL", "type": "BOOLEAN", "links": []}],
         "title": title, "properties": {"Node name for S&R": "ComfyMathExpression"},
         "widgets_values": [expr], "widgets_values_named": {"expression": expr}, "color": color[0], "bgcolor": color[1]}
    sg["nodes"].append(n)
    inner[n["id"]] = n
    return n


def set_expr(node_id, expr, title):
    n = inner[node_id]
    n["widgets_values"] = [expr]
    n["widgets_values_named"] = {"expression": expr}
    n["title"] = title


def reroute_origin(link_id, new_origin, new_slot):
    l = links[link_id]
    old = inner[l["origin_id"]]["outputs"][l["origin_slot"]]
    old["links"].remove(link_id)
    l["origin_id"], l["origin_slot"] = new_origin, new_slot
    inner[new_origin]["outputs"][new_slot]["links"].append(link_id)


# ------------------------------------------------------------------ 1. 4k+1 chunk math
F = inner[686]
F["title"] = "INTERNAL · F = Frames per sampler (81 · 4k+1로 자동 정렬)"
f4 = math_node("max(5, 4*floor((a-1)/4)+1)", "INTERNAL · F → 4k+1 정렬 (Wan은 4k+1 프레임만 디코드)",
               [F["pos"][0], F["pos"][1] + 140])
add_link(686, 0, f4["id"], 0, "INT")
for l_id in (1145, 1146, 1147, 1148, 1149):
    reroute_origin(l_id, f4["id"], 1)
set_expr(655, "min(b, max(1, 4*ceil((a-1)/4)+1))", "AUTO · Chunk 1 frames = min(F, 4k+1 ≥ total)")
set_expr(656, "min(b, max(1, 4*ceil((a-b)/4)+1))", "AUTO · Chunk 2 frames = min(F, 4k+1 ≥ total-F+1)")
set_expr(657, "min(b, max(1, 4*ceil((a-2*b+1)/4)+1))", "AUTO · Chunk 3 frames = min(F, 4k+1 ≥ total-2F+2)")
set_expr(658, "a>b", "AUTO · Need Chunk 2? total > F")
set_expr(659, "a>2*b-1", "AUTO · Need Chunk 3? total > 2F-1")
inner[664]["title"] = "FINAL TRIM | 4k+1 chunk 결과 → 정확히 target frames"

# ------------------------------------------------------------------ 2. even output size (H.264 needs even W/H)
set_expr(670, "max(2, round(a*b/c/2)*2)", "KEEP ASPECT | custom width × source height / source width (짝수)")
rs = inner[666]
ew = math_node("max(2, round(a/2)*2)", "EVEN · Output Width (H.264)", [rs["pos"][0] - 460, rs["pos"][1] + 200])
eh = math_node("max(2, round(a/2)*2)", "EVEN · Output Height (H.264)", [rs["pos"][0] - 460, rs["pos"][1] + 400])
for l_id, en, src in ((1103, ew, 669), (1104, eh, 671)):
    l = links[l_id]
    add_link(src, 0, en["id"], 0, "INT")
    reroute_origin(l_id, en["id"], 1)
rs["title"] = "RESTORE RESOLUTION | Lanczos · Source 또는 Custom (짝수 보정)"

# ------------------------------------------------------------------ 3. new MAIN CONTROL inputs
named = dict(inst["widgets_values_named"])


def add_input(name, typ, label, target, target_input, default):
    idx = len(sg["inputs"])
    s = {"id": str(uuid.uuid5(NS, "MAIN CONTROL/in/" + name)), "name": name, "type": typ, "linkIds": [], "localized_name": name, "label": label, "pos": [0, 0]}
    sg["inputs"].append(s)
    tn = inner[target]
    slot = next((i for i, x in enumerate(tn["inputs"]) if x["name"] == target_input), None)
    if slot is None:
        tn["inputs"].append({"localized_name": target_input, "name": target_input, "type": typ, "widget": {"name": target_input}, "link": None})
        slot = len(tn["inputs"]) - 1
    l = add_link(-10, idx, target, slot, typ)
    s["linkIds"].append(l["id"])
    inst["inputs"].append({"label": label, "name": name, "type": typ, "widget": {"name": name}, "link": None})
    named[name] = default


add_input("distill_model", "COMBO", "01 MODEL · Distilled Model (증류 ON일 때)", 688, "unet_name", inner[688]["widgets_values"][0])
add_input("clip_name", "COMBO", "08 FILES · Text Encoder (UMT5)", 610, "clip_name", inner[610]["widgets_values"][0])
add_input("clip_vision_name", "COMBO", "08 FILES · CLIP Vision", 613, "clip_name", inner[613]["widgets_values"][0])
add_input("vae_name", "COMBO", "08 FILES · VAE", 614, "vae_name", inner[614]["widgets_values"][0])

relabel = {
    "use_distilled": "01 MODEL · 증류 모델 사용 (ON = Distilled 10 steps / OFF = Model + LoRA 6 steps)",
    "diffusion_model": "01 MODEL · Model (증류 OFF일 때)",
    "lora_name": "01 MODEL · LoRA (증류 OFF일 때)",
    "lora_strength": "01 MODEL · LoRA Strength (증류 OFF일 때)",
    "use_custom_duration": "03 VIDEO · Length Mode · Custom (OFF = Source Video · 최대 3F-2 = 241f)",
}
order = ["reference_image", "driving_video", "use_distilled", "distill_model", "diffusion_model", "lora_name", "lora_strength",
         "positive_prompt", "negative_prompt", "motion_prompt", "use_custom_duration", "duration_seconds",
         "use_custom_resolution", "custom_width", "custom_height", "keep_aspect_ratio", "use_custom_fps", "custom_fps",
         "reference_image_strength", "pose_strength", "seed", "seed_control", "clip_name", "clip_vision_name", "vae_name"]
old_names = [s["name"] for s in sg["inputs"]]
assert sorted(old_names) == sorted(order), set(old_names) ^ set(order)
new_idx = {n: i for i, n in enumerate(order)}
by_name = {s["name"]: s for s in sg["inputs"]}
x0, y0 = sg["inputNode"]["bounding"][0] + sg["inputNode"]["bounding"][2] - 24, sg["inputNode"]["bounding"][1] + 24
sg["inputs"] = [by_name[n] for n in order]
for i, s in enumerate(sg["inputs"]):
    s["pos"] = [x0, y0 + 20 * i]
    if s["name"] in relabel:
        s["label"] = relabel[s["name"]]
sg["inputNode"]["bounding"][3] = 48 + 20 * len(order)
for l in sg["links"]:
    if l["origin_id"] == -10:
        l["origin_slot"] = new_idx[old_names[l["origin_slot"]]]
inst_by = {s["name"]: s for s in inst["inputs"]}
inst["inputs"] = [inst_by[n] for n in order]
for s in inst["inputs"]:
    if s["name"] in relabel:
        s["label"] = relabel[s["name"]]
for l in wf["links"]:
    if l[3] == 638:
        l[4] = new_idx[old_names[l[4]]]
types = {s["name"]: s["type"] for s in sg["inputs"]}
wnames = [n for n in order if types[n] in WIDGET]
inst["widgets_values"] = [named[n] for n in wnames]
inst["widgets_values_named"] = {n: named[n] for n in wnames}
inst["size"] = [600, 1320]

# ------------------------------------------------------------------ 4. outputs, comparison labels
top[246]["widgets_values"][0] = "video/Wan_Animate2"
top[246]["widgets_values_named"]["filename_prefix"] = "video/Wan_Animate2"
top[292]["widgets_values"][0] = "video/Wan_Animate2_compare"
top[292]["widgets_values_named"]["filename_prefix"] = "video/Wan_Animate2_compare"
top[291]["title"] = "(선택) 결과 / 원본 비교"
top[291]["inputs"][0]["label"] = "Result (left)"
top[291]["inputs"][1]["label"] = "Driving (right)"
st["inputs"][0]["label"] = "Result (left)"
st["inputs"][1]["label"] = "Driving (right)"
top[292]["title"] = "(선택) 결과 / 원본 비교 저장"
for g in wf["groups"]:
    if g["title"].startswith("07 OUTPUT"):
        g["title"] = "07 OUTPUT (결과 / 원본 비교는 선택)"

# ------------------------------------------------------------------ 5. notes
AN = "https://huggingface.co/Comfy-Org/Wan-Animate-2/resolve/main"
top[574]["widgets_values"][0] = top[574]["widgets_values_named"]["text"] = """# Wan Animate 2 — 사용 순서

`1. Reference Image` → `2. Driving Video` → `3. MAIN CONTROL` → `4. Final Output`

Reference Image와 Driving Video를 넣고 **MAIN CONTROL 한 곳에서** Model / LoRA / Prompt / Length·Resolution·FPS Mode / Strength / Seed를 조절한 뒤 Generate 하면 됩니다. Chunk 길이(4k+1), continuation, overlap trim, 최종 frame trim, 원본 해상도 복원, 오디오 및 FPS 유지는 전부 자동입니다.

## MAIN CONTROL에서 조절하는 항목

- **01 MODEL** · 증류 모델 사용 · Distilled Model · Model · LoRA · LoRA Strength
- **02 PROMPT** · Positive / Negative / Motion Prompt
- **03 VIDEO** · Length Mode · Duration
- **04 RESOLUTION** · Resolution Mode · Custom Width / Height · Keep Aspect Ratio
- **05 FPS** · FPS Mode · Custom FPS
- **06 REFERENCE** · Reference Strength · Motion / Pose Strength
- **07 SEED** · Seed · Seed Mode
- **08 FILES** · Text Encoder · CLIP Vision · VAE (파일명이 다를 때만)

`증류 모델 사용` ON(기본)이면 **Distilled Model + 10 steps**, OFF면 **Model + LoRA + 6 steps**로 자동 전환됩니다. OFF 쪽의 Model / LoRA 값은 ON일 때 무시됩니다.

Sampler, Scheduler, CFG, Cache, Context Window, Model Shift, Pose Window, Frames per sampler(F)는 검증된 기본값으로 MAIN CONTROL 내부에 숨겨져 있습니다.

## Source / Custom

- **Source (기본값)** — Driving Video의 frame count · 해상도 · FPS를 그대로 사용합니다. 출력 프레임 수 = 원본 프레임 수 (최대 `3F-2` = 241f).
- **Custom** — 해당 Mode 토글을 켠 항목만 override 됩니다. (`Duration × FPS` = target frames, 원본보다 길면 마지막 포즈를 유지, Custom Width/Height는 마지막 Lanczos 복원 단계에 짝수로 맞춰 적용)

Wan 내부 생성은 비율을 유지한 약 480p Canvas에서 이루어지므로 GPU 효율은 그대로입니다.

`(선택) 결과 / 원본 비교`는 지워도 본 파이프라인에는 영향이 없습니다."""

m575 = top[575]["widgets_values"][0]
m575 = m575.replace(
    "## 1. Diffusion Model — 필수\n\n",
    f"## 1-A. Distilled Model — 기본값 (증류 모델 사용 ON)\n\n[⬇ wan_animate_2_distill_int8_convrot.safetensors]({AN}/diffusion_models/wan_animate_2_distill_int8_convrot.safetensors?download=true)\n\n"
    "- 저장 위치: `ComfyUI/models/diffusion_models/`\n- LoRA 없이 10 steps로 동작하는 공식 증류 본체\n\n## 1-B. Diffusion Model — 증류 OFF일 때\n\n")
m575 = m575.replace("## 2. 4-Step 속도 LoRA — 필수", "## 2. 4-Step 속도 LoRA — 증류 OFF일 때")
m575 = m575.replace("[⬇ clip_vision_h.safetensors (약 1.26GB)](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors?download=true)",
                    f"[⬇ clip_vision_h.safetensors (약 1.26GB)]({AN}/clip_vision/clip_vision_h.safetensors?download=true)")
m575 = m575.replace("- Chunk 2·3 길이와 실행 여부는 내부 변수 F에서 자동 계산됩니다. 사용자는 Chunk 길이를 직접 조절하지 않습니다.",
                    "- Chunk 2·3 길이와 실행 여부는 내부 변수 F에서 자동 계산됩니다. 사용자는 Chunk 길이를 직접 조절하지 않습니다.\n"
                    "- 내 PC에 파일이 다른 이름으로 저장돼 있으면 MAIN CONTROL의 `01 MODEL` · `08 FILES`에서 직접 고르면 됩니다.")
top[575]["widgets_values"][0] = top[575]["widgets_values_named"]["text"] = m575

top[540]["widgets_values"][0] = top[540]["widgets_values_named"]["text"] = """## 내부 고정값 (MAIN CONTROL 안에 숨김)

weight dtype, sampler, scheduler, steps(증류 10 / 일반 6), denoise, model shift, context window, cache, CFG, pose start/end는 기존 검증값 그대로 내부에 유지됩니다.

## Frames per sampler = 내부 변수 F

Chunk 길이 / threshold / overlap 계산은 MAIN CONTROL 내부의 `INTERNAL · F` 노드 **하나**에서 전부 파생됩니다. (기본 `F = 81`, 자동으로 4k+1 정렬)

Wan은 chunk마다 **4k+1 프레임만** 디코드하므로 모든 chunk 길이를 4k+1로 올림한 뒤 마지막에 정확히 잘라냅니다.

- Chunk 1 = `min(F, 4k+1 ≥ total)`
- Chunk 2 = `min(F, 4k+1 ≥ total-F+1)` · 앞 1프레임은 continuation overlap으로 제거
- Chunk 3 = `min(F, 4k+1 ≥ total-2F+2)` · 앞 1프레임 제거
- Need Chunk 2 = `total > F` · Need Chunk 3 = `total > 2F-1`
- 최대 출력 길이 = `3F-2` (F=81 → 241f)

VRAM이 부족하면 MAIN CONTROL을 열고 `F` 값만 낮추면 됩니다. 24GB=81 / 16GB=49 / 12GB=33이 시작값이며, 나머지 수식은 자동으로 따라갑니다."""

# ------------------------------------------------------------------ 6. bookkeeping
sg["revision"] = 4
wf["revision"] = 4
state["lastNodeId"] = max(state["lastNodeId"], max(n["id"] for n in sg["nodes"]))
wf["last_node_id"] = max(wf["last_node_id"], state["lastNodeId"])
wf["last_link_id"] = max(wf["last_link_id"], state["lastLinkId"])
for s in wf["definitions"]["subgraphs"]:
    s["state"]["lastNodeId"] = wf["last_node_id"]
    s["state"]["lastLinkId"] = wf["last_link_id"]
wf["extra"]["creator_ui_audit"] = {
    "date": "2026-09-24",
    "revision": 4,
    "changes": [
        "Chunk lengths rounded up to 4k+1 (Wan decodes 4k+1 frames); F aligned to 4k+1; chunk 3 threshold total > 2F-1. "
        "Fixes short output (e.g. 100f source -> 97f) and the 1-frame pose slip in chunk 3",
        "Output width/height forced even (Keep Aspect could yield odd height, which H.264 rejects)",
        "Distilled model file selectable in MAIN CONTROL; hidden Text Encoder / CLIP Vision / VAE loaders exposed as 08 FILES",
        "MAIN CONTROL inputs reordered so the distilled toggle sits under 01 MODEL",
        "Model notes: distilled model download link, CLIP Vision link from Comfy-Org/Wan-Animate-2",
        "Comparison inputs relabelled Result (left) / Driving (right); output filename prefixes video/Wan_Animate2*",
    ],
    "runtime_verified": "dry-run only: ComfyUI v0.31.1 + frontend 1.48.7 load, graphToPrompt, server validation and execution "
                        "with stubbed model math; 100/170/50-frame driving videos return 100/170/50 frames with frame-exact pose order. "
                        "Not GPU-rendered; motion quality unverified.",
}
json.dump(wf, open(os.path.join(HERE, "..", "workflows", "WAN_Animate2_CreatorUI.json"), "w"), ensure_ascii=False, indent=2)
print("ok", len(sg["nodes"]), "main nodes;", len(sg["inputs"]), "inputs")
