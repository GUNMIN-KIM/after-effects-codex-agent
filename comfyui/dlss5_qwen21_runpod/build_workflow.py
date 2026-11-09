"""Build a ComfyUI UI-format workflow: Qwen-Image 2.1 (bf16) + DLSS5 Edit LoRA,
2-stage (look @ ~2MP -> detail refine @ ~4MP), plate-size match output.
Node/slot specs copied from Comfy-Org/workflow_templates (Qwen Image 2.1 edit template).
"""
import json, sys, uuid

OUT = sys.argv[1]

HF = "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main"
UNET = "qwen_image_2.1_bf16.safetensors"
TE = "qwen3vl_8b_bf16.safetensors"
VAE = "qwen_image_2.1_vae_bf16.safetensors"
LORA = "qwen21_dlss5_edit.safetensors"

PROMPT_S1 = (
    "dlss5. Re-render <image1> as a real high-end studio photograph with DLSS 5 style neural rendering. "
    "Physically accurate lighting with soft contact shadows under the runners, true mirror-chrome reflections "
    "on the scrollwork runners, bumpers and trim, pearlescent white automotive paint with clear-coat highlights, "
    "real cream leather seats with visible stitching, piping and natural creases, dark brown leather armrests, "
    "glass headlight lenses with warm glowing bulbs and visible reflectors, a polished silver reindeer hood ornament, "
    "pale blue gift boxes with satin burgundy ribbons. "
    "Keep the exact composition, camera angle, framing, proportions and every curl and ornament detail unchanged; "
    "same number of seats and gift boxes. Keep the flat, evenly lit chroma-key green background and floor unchanged, "
    "without adding extra green color cast on the white paint or the seats. "
    "Crisp sharp edges, rich micro-detail, no blur, no noise."
)
PROMPT_S2 = (
    "dlss5. <image1> High-resolution detail refinement of this photograph. Sharpen and enrich fine micro-detail: "
    "leather grain and stitching, chrome scrollwork reflections, paint clear-coat, headlight glass and reflectors, "
    "satin ribbon weave, reindeer ornament engraving. Keep everything else identical: same composition, shapes, "
    "colors, lighting and the flat chroma-key green background. No new objects, no blur, no noise."
)
NEG = (
    "blurry, soft focus, smeared details, plastic CG look, cartoon, changed shape, warped ornaments, extra objects, "
    "green color cast on paint, uneven green background, vignette, noise, jpeg artifacts"
)

nodes, links = [], []
_nid = [0]
_lid = [0]


def node(ntype, pos, size, inputs, outputs, widgets, title=None, props_extra=None, color=None, mode=0):
    _nid[0] += 1
    n = {
        "id": _nid[0], "type": ntype, "pos": pos, "size": size, "flags": {}, "order": 0, "mode": mode,
        "inputs": [dict(i, link=None) for i in inputs],
        "outputs": [dict(o, links=[]) for o in outputs],
        "properties": dict({"Node name for S&R": ntype}, **(props_extra or {})),
        "widgets_values": widgets,
    }
    if title:
        n["title"] = title
    if color:
        n["color"], n["bgcolor"] = color
    nodes.append(n)
    return n


def I(name, typ, widget=False, optional=False):
    d = {"localized_name": name.split(".")[-1], "name": name, "type": typ}
    if widget:
        d["widget"] = {"name": name}
    if optional:
        d["shape"] = 7
    return d


def O(name, typ):
    return {"localized_name": name, "name": name, "type": typ}


def link(src, src_slot, dst, dst_input):
    _lid[0] += 1
    lid = _lid[0]
    slot_idx = [i["name"] for i in dst["inputs"]].index(dst_input)
    typ = src["outputs"][src_slot]["type"]
    dst["inputs"][slot_idx]["link"] = lid
    src["outputs"][src_slot]["links"].append(lid)
    links.append([lid, src["id"], src_slot, dst["id"], slot_idx, typ])


def model_meta(name, sub):
    return {"models": [{"name": name, "url": f"{HF}/{sub}/{name}", "directory": sub}]}


GREEN = ("#232", "#353")
BLUE = ("#223", "#335")
PURPLE = ("#323", "#535")

# ---------------- notes ----------------
NOTE_USAGE = """## DLSS5 스타일 실사화: Qwen-Image 2.1 bf16, 2-Stage, RunPod 최고 품질

**흐름**
1. **STAGE 1 (약 2MP)**: 원본 → DLSS5 룩(조명, 재질, 반사)
2. **STAGE 2 (약 4MP, 네이티브 2K)**: 1단계 결과를 확대한 뒤 낮은 denoise로 마이크로 디테일만 다시 생성
3. **원본 크기 매칭**: 결과를 원본 해상도로 슈퍼샘플링해 AE에서 플레이트에 1:1로 겹칠 수 있게 함

**디테일 노브 (중요)**
| 노브 | 위치 | 기본값 | 효과 |
|---|---|---|---|
| denoise | KSampler S1 | 0.85 | 낮출수록 원본 형태와 디테일 유지 (0.7~1.0) |
| denoise | KSampler S2 | 0.30 | 높일수록 디테일이 더 생기지만 형태가 변할 수 있음 (0.2~0.45) |
| strength | DLSS5 LoRA | 1.0 | 0.6~0.8이면 은은하게, 1.0이면 풀 DLSS5 |
| megapixels | S2 Resize | 3.9 | 모델 최대 2048² 예산. 이보다 높이지 말 것 |

- cfg는 1로 고정합니다(Qwen 2.1 공식 설정). cfg가 1이면 negative는 무시됩니다.
- 시드는 fixed입니다. 룩이 마음에 들면 S1 시드를 고정해 두고 S2만 조절하세요.
- STAGE 2를 빼려면 S2 그룹을 선택한 뒤 Ctrl+B로 bypass하세요.
- LoRA가 없으면 LoRA 노드를 Ctrl+B로 bypass하세요. 프롬프트만으로도 동작하지만 효과는 약합니다.
"""

NOTE_MODELS = f"""## 모델 파일 (RunPod: download_models_runpod.sh 실행)

**diffusion_models**
- [{UNET}]({HF}/diffusion_models/{UNET}) (13.25 GB)

**text_encoders**
- [{TE}]({HF}/text_encoders/{TE}) (16.33 GB)

**vae**
- [{VAE}]({HF}/vae/{VAE}) (644 MB)

**loras**
- Civitai "Qwen 2.1 - DLSS 5 Edit / Slider"의 **Edit(img2img) 버전**
  → `models/loras/{LORA}`로 저장 (트리거 `dlss5`는 프롬프트에 이미 들어 있음)

**권장 GPU**: 48GB 이상 (L40S, RTX 6000 Ada, A100 80GB, H100)
24~32GB(4090/5090)에서도 동작하지만 텍스트 인코더를 오프로드하면서 느려집니다.
ComfyUI는 Qwen Image 2.1 노드가 들어간 최신 버전이어야 합니다.
"""

note1 = node("MarkdownNote", [-480, 0], [440, 620], [], [], [NOTE_USAGE], title="사용법 / 디테일 노브")
note2 = node("MarkdownNote", [-480, 660], [440, 520], [], [], [NOTE_MODELS], title="모델 다운로드")

# ---------------- input ----------------
load = node("LoadImage", [0, 0], [400, 460], [], [O("IMAGE", "IMAGE"), O("MASK", "MASK")],
            ["sleigh_greenscreen.png", "image"], title="원본 (그린스크린 CG)")
size = node("GetImageSize", [0, 520], [230, 120], [I("image", "IMAGE")],
            [O("width", "INT"), O("height", "INT"), O("batch_size", "INT")], [], title="원본 크기")

# ---------------- models ----------------
unet = node("UNETLoader", [460, 0], [440, 90], [I("unet_name", "COMBO", True), I("weight_dtype", "COMBO", True)],
            [O("MODEL", "MODEL")], [UNET, "default"], props_extra=model_meta(UNET, "diffusion_models"), color=BLUE)
lora = node("LoraLoaderModelOnly", [460, 130], [440, 110],
            [I("model", "MODEL"), I("lora_name", "COMBO", True), I("strength_model", "FLOAT", True)],
            [O("MODEL", "MODEL")], [LORA, 1.0], title="DLSS5 Edit LoRA (Civitai)", color=PURPLE)
cache = node("QwenImage21Cache", [460, 280], [440, 90],
             [I("model", "MODEL"), I("device", "COMBO", True), I("dtype", "COMBO", True)],
             [O("MODEL", "MODEL")], ["auto", "default"])
clip = node("CLIPLoader", [460, 410], [440, 120],
            [I("clip_name", "COMBO", True), I("type", "COMBO", True), I("device", "COMBO", True)],
            [O("CLIP", "CLIP")], [TE, "qwen_image", "default"], props_extra=model_meta(TE, "text_encoders"), color=BLUE)
vae = node("VAELoader", [460, 570], [440, 70], [I("vae_name", "COMBO", True)], [O("VAE", "VAE")],
           [VAE], props_extra=model_meta(VAE, "vae"), color=BLUE)


def stage(tag, x, mp, prompt, steps, denoise, seed, save_prefix, venc_title):
    rs = node("ImageScaleToTotalPixels", [x, 0], [300, 110],
              [I("image", "IMAGE"), I("upscale_method", "COMBO", True), I("megapixels", "FLOAT", True),
               I("resolution_steps", "INT", True)],
              [O("IMAGE", "IMAGE")], ["lanczos", mp, 32], title=f"{tag} Resize (×32 정렬)")
    enc = node("TextEncodeQwenImage21", [x, 150], [460, 520],
               [I("clip", "CLIP"), I("images.image_1", "IMAGE", optional=True), I("vae", "VAE", optional=True),
                I("prompt", "STRING", True), I("negative_prompt", "STRING", True), I("resolution", "INT", True),
                I("images.image_2", "IMAGE", optional=True)],
               [O("positive", "CONDITIONING"), O("negative", "CONDITIONING"), O("latent", "LATENT")],
               [prompt, NEG, 0], title=f"{tag} Prompt (resolution 0 = 입력 크기 그대로)", color=GREEN)
    venc = node("VAEEncode", [x, 710], [230, 50], [I("pixels", "IMAGE"), I("vae", "VAE")],
                [O("LATENT", "LATENT")], [], title=venc_title)
    ks = node("KSampler", [x + 500, 0], [320, 280],
              [I("model", "MODEL"), I("positive", "CONDITIONING"), I("negative", "CONDITIONING"),
               I("latent_image", "LATENT"), I("seed", "INT", True), I("steps", "INT", True),
               I("cfg", "FLOAT", True), I("sampler_name", "COMBO", True), I("scheduler", "COMBO", True),
               I("denoise", "FLOAT", True)],
              [O("LATENT", "LATENT")], [seed, "fixed", steps, 1, "euler", "simple", denoise],
              title=f"KSampler {tag}", color=GREEN)
    dec = node("VAEDecode", [x + 500, 330], [230, 50], [I("samples", "LATENT"), I("vae", "VAE")],
               [O("IMAGE", "IMAGE")], [])
    save = node("SaveImage", [x + 500, 430], [420, 340], [I("images", "IMAGE"), I("filename_prefix", "STRING", True)],
                [], [save_prefix])
    link(rs, 0, enc, "images.image_1")
    link(rs, 0, venc, "pixels")
    link(clip, 0, enc, "clip")
    link(vae, 0, enc, "vae")
    link(vae, 0, venc, "vae")
    link(vae, 0, dec, "vae")
    link(cache, 0, ks, "model")
    link(enc, 0, ks, "positive")
    link(enc, 1, ks, "negative")
    link(venc, 0, ks, "latent_image")
    link(ks, 0, dec, "samples")
    link(dec, 0, save, "images")
    return rs, dec, [rs, enc, venc, ks, dec, save]


link(unet, 0, lora, "model")
link(lora, 0, cache, "model")
link(load, 0, size, "image")

s1_rs, s1_dec, s1_nodes = stage("S1", 960, 2.0, PROMPT_S1, 50, 0.85, 20261109, "DLSS5/S1_look", "S1 원본 latent (디테일 락)")
link(load, 0, s1_rs, "image")
s2_rs, s2_dec, s2_nodes = stage("S2", 1940, 3.9, PROMPT_S2, 30, 0.30, 20261110, "DLSS5/S2_2K", "S2 S1결과 latent (디테일 락)")
link(s1_dec, 0, s2_rs, "image")

# ---------------- plate match + compare ----------------
scale = node("ImageScale", [2920, 0], [300, 160],
             [I("image", "IMAGE"), I("upscale_method", "COMBO", True), I("width", "INT", True),
              I("height", "INT", True), I("crop", "COMBO", True)],
             [O("IMAGE", "IMAGE")], ["lanczos", 2000, 848, "disabled"], title="원본 크기로 매칭 (AE 플레이트 1:1)")
save_plate = node("SaveImage", [2920, 210], [420, 340], [I("images", "IMAGE"), I("filename_prefix", "STRING", True)],
                  [], ["DLSS5/plate_match"])
compare = node("ImageCompare", [3380, 0], [700, 560],
               [I("image_a", "IMAGE", optional=True), I("image_b", "IMAGE", optional=True)], [], [],
               title="원본 vs DLSS5")
link(s2_dec, 0, scale, "image")
link(size, 0, scale, "width")
link(size, 1, scale, "height")
link(scale, 0, save_plate, "images")
link(load, 0, compare, "image_a")
link(scale, 0, compare, "image_b")


# ---------------- order (topological) ----------------
def topo():
    by_id = {n["id"]: n for n in nodes}
    deps = {n["id"]: set() for n in nodes}
    for l in links:
        deps[l[3]].add(l[1])
    order, done = [], set()
    while len(order) < len(nodes):
        ready = sorted(i for i in deps if i not in done and deps[i] <= done)
        assert ready, "cycle"
        for i in ready:
            done.add(i)
            order.append(i)
    for k, i in enumerate(order):
        by_id[i]["order"] = k


topo()


def bbox(ns, pad=40, title_h=50):
    x0 = min(n["pos"][0] for n in ns) - pad
    y0 = min(n["pos"][1] for n in ns) - pad - title_h
    x1 = max(n["pos"][0] + n["size"][0] for n in ns) + pad
    y1 = max(n["pos"][1] + n["size"][1] for n in ns) + pad
    return [x0, y0, x1 - x0, y1 - y0]


groups = [
    {"id": 1, "title": "① 입력", "bounding": bbox([load, size]), "color": "#3f789e", "font_size": 24, "flags": {}},
    {"id": 2, "title": "② 모델: bf16 풀정밀도", "bounding": bbox([unet, lora, cache, clip, vae]),
     "color": "#8A8", "font_size": 24, "flags": {}},
    {"id": 3, "title": "③ STAGE 1: DLSS5 룩 (약 2MP)", "bounding": bbox(s1_nodes), "color": "#b58b2a",
     "font_size": 24, "flags": {}},
    {"id": 4, "title": "④ STAGE 2: 2K 디테일 리파인 (약 4MP)", "bounding": bbox(s2_nodes), "color": "#a1309b",
     "font_size": 24, "flags": {}},
    {"id": 5, "title": "⑤ 원본 크기 매칭 + 비교", "bounding": bbox([scale, save_plate, compare]), "color": "#444",
     "font_size": 24, "flags": {}},
]

wf = {
    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "dlss5_qwen21_2k_detail")),
    "revision": 0,
    "last_node_id": _nid[0],
    "last_link_id": _lid[0],
    "nodes": nodes,
    "links": links,
    "groups": groups,
    "config": {},
    "extra": {"ds": {"scale": 0.45, "offset": [560, 120]}},
    "version": 0.4,
}

# ---------------- validation ----------------
by_id = {n["id"]: n for n in nodes}
lids = set()
for lid, o, os_, t, ts, typ in links:
    assert lid not in lids
    lids.add(lid)
    src, dst = by_id[o], by_id[t]
    assert src["outputs"][os_]["type"] == typ, (lid, src["type"])
    assert lid in src["outputs"][os_]["links"]
    assert dst["inputs"][ts]["link"] == lid
    dtyp = dst["inputs"][ts]["type"]
    assert dtyp == typ or (dtyp == "INT" and typ == "INT"), (lid, dst["type"], dtyp, typ)
for n in nodes:
    for i in n["inputs"]:
        if i["link"] is None and "widget" not in i and i.get("shape") != 7:
            raise SystemExit(f"unconnected required input {n['type']}.{i['name']}")
        if i["link"] is not None:
            assert i["link"] in lids
    nw = sum(1 for i in n["inputs"] if "widget" in i)
    if n["type"] == "KSampler":
        assert len(n["widgets_values"]) == nw + 1  # + control_after_generate
    elif n["type"] not in ("MarkdownNote", "LoadImage"):
        assert len(n["widgets_values"]) == nw, (n["type"], n["widgets_values"], nw)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=1)
print("nodes", len(nodes), "links", len(links), "->", OUT)
for n in sorted(nodes, key=lambda n: n["order"]):
    print(f'  [{n["order"]:2}] #{n["id"]:2} {n["type"]:24} {n.get("title","")}')
