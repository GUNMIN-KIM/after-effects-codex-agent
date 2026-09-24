"""Build the Wan VACE Creator UI workflows (1.3B/14B background extension + inpaint 2x pixel-lock)."""
import copy
import json
import os
import sys

from wfbuild import Graph, Subgraph, COLORS, top_links, sid

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "source")
OUT = os.path.join(HERE, "..", "workflows")

ANIM = json.load(open(os.path.join(SRC, "WAN_Animate2_rev3_original.json")))
STITCH = copy.deepcopy(next(s for s in ANIM["definitions"]["subgraphs"] if s["name"] == "Video Stitch"))

HF = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"
KJ = "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main"
MODELS = {
    "wan2.1_vace_14B_fp16.safetensors": ("diffusion_models", f"{HF}/diffusion_models/wan2.1_vace_14B_fp16.safetensors"),
    "wan2.1_vace_1.3B_fp16.safetensors": ("diffusion_models", f"{HF}/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors"),
    "Wan21_CausVid_14B_T2V_lora_rank32.safetensors": ("loras", f"{KJ}/Wan21_CausVid_14B_T2V_lora_rank32.safetensors"),
    "Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors": ("loras", f"{KJ}/Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors"),
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": ("text_encoders", f"{HF}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    "wan_2.1_vae.safetensors": ("vae", f"{HF}/vae/wan_2.1_vae.safetensors"),
}


def models_prop(name):
    d, u = MODELS[name]
    return {"models": [{"name": name, "url": u, "directory": d}]}


def build_main(ids, cfg):
    sg = Subgraph(ids, "MAIN CONTROL",
                  "Wan VACE — source/mask/reference, auto 16px canvas, 4k+1 length, gray-fill control, "
                  "pixel-lock output, source FPS/audio/length in one panel.")
    I = sg.add_input
    I("source_video", "VIDEO", "Source Video")
    I("mask_video", "VIDEO", "Mask Video")
    I("reference_image", "IMAGE", "Reference Image (optional)")
    I("unet_name", "COMBO", "01 MODEL · VACE Model", cfg["unet"])
    I("lora_name", "COMBO", "01 MODEL · Speed LoRA (CausVid)", cfg["lora"])
    I("lora_strength", "FLOAT", "01 MODEL · Speed LoRA Strength", cfg["lora_strength"])
    I("turbo", "BOOLEAN", f"01 MODEL · Turbo · LoRA {cfg['turbo_steps']} steps CFG 1 (OFF = 20 steps CFG 6)", True)
    I("positive_prompt", "STRING", "02 PROMPT · Positive Prompt", cfg["positive"])
    I("negative_prompt", "STRING", "02 PROMPT · Negative Prompt", cfg["negative"])
    I("use_custom_duration", "BOOLEAN", "03 VIDEO · Length Mode · Custom (OFF = Source Video)", False)
    I("duration_seconds", "FLOAT", "03 VIDEO · Duration (sec · 소스 길이 이내)", 5.0)
    I("canvas_720p", "BOOLEAN", "04 RESOLUTION · Generation Canvas 720p (OFF = 480p · 1.3B는 OFF)", cfg["canvas_720p"])
    I("output_scale", "FLOAT", "04 RESOLUTION · Output Scale (Source × N)", cfg["output_scale"])
    I("use_custom_resolution", "BOOLEAN", "04 RESOLUTION · Mode · Custom (OFF = Source × Scale)", False)
    I("custom_width", "INT", "04 RESOLUTION · Custom Width", 1920)
    I("custom_height", "INT", "04 RESOLUTION · Custom Height", 1080)
    I("keep_aspect_ratio", "BOOLEAN", "04 RESOLUTION · Keep Aspect Ratio", True)
    I("use_custom_fps", "BOOLEAN", "05 FPS · Mode · Custom (OFF = Source)", False)
    I("custom_fps", "FLOAT", "05 FPS · Custom FPS", 30.0)
    I("invert_mask", "BOOLEAN", "06 MASK · Invert (OFF = 흰색/빨강 = 생성 영역)", False)
    I("mask_expand", "INT", "06 MASK · Expand (px · canvas 기준)", cfg["mask_expand"])
    I("mask_block_align", "BOOLEAN", "06 MASK · 8px Block Align", False)
    I("pixel_lock", "BOOLEAN", "06 MASK · Pixel Lock (마스크 밖 = 원본 픽셀)", True)
    I("vace_strength", "FLOAT", "07 VACE · Control Strength", 1.0)
    I("seed", "INT", "08 SEED · Seed", cfg["seed"])
    I("seed_control", "COMBO", "08 SEED · Seed Mode", "fixed")
    I("clip_name", "COMBO", "09 FILES · Text Encoder", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
    I("vae_name", "COMBO", "09 FILES · VAE", "wan_2.1_vae.safetensors")
    sg.add_output("video", "VIDEO")
    sg.add_output("control_preview", "VIDEO", "Control / Mask Preview")

    A = sg.add
    L = sg.link
    F = sg.from_input
    X = [0, 470, 940, 1410, 1880, 2350, 2820, 3290, 3760]

    def math(expr, title, pos, n=1, color="control", size=(430, 170)):
        return A("ComfyMathExpression", title, pos, size, {"expression": expr}, color=color, n_values=n)

    def switch(t, title, pos, color="control"):
        return A("ComfySwitchNode", title, pos, (430, 130), color=color, match_type=t)

    def resize(title, pos, method, mtype="IMAGE", color="mask"):
        return A("ResizeImageMaskNode", title, pos, (430, 160),
                 {"resize_type": "scale dimensions", "resize_type.crop": "disabled", "scale_method": method},
                 color=color, match_type=mtype)

    # ---------------- 01 SOURCE · LENGTH · FPS
    vsrc = A("GetVideoComponents", "Source Components | frames · audio · fps", (X[0], 0), (430, 140), color="video")
    F("source_video", vsrc, "video")
    ssize = A("GetImageSize", "Source Metadata | width · height · total frames", (X[0], 200), (430, 130), color="video")
    L(vsrc, "images", ssize, "image")

    ui_fps = A("PrimitiveFloat", "UI · Custom FPS", (X[0], 400), (430, 90), {"value": 30.0}, color="control")
    F("custom_fps", ui_fps, "value")
    fps_sel = switch("FLOAT", "FPS MODE | Source FPS or Custom FPS", (X[0], 540))
    L(vsrc, "fps", fps_sel, "on_false"); L(ui_fps, 0, fps_sel, "on_true"); F("use_custom_fps", fps_sel, "switch")

    ui_dur = A("PrimitiveFloat", "UI · Duration (sec)", (X[0], 720), (430, 90), {"value": 5.0}, color="control")
    F("duration_seconds", ui_dur, "value")
    cust_len = math("max(1, min(c, round(a*b)))", "CUSTOM DURATION | round(sec × FPS) · 소스 프레임 이내", (X[0], 860), 3)
    L(ui_dur, 0, cust_len, "values.a"); L(fps_sel, 0, cust_len, "values.b"); L(ssize, "batch_size", cust_len, "values.c")
    target = switch("INT", "LENGTH MODE | Source Frames or Custom Duration", (X[0], 1080))
    L(ssize, "batch_size", target, "on_false"); L(cust_len, "INT", target, "on_true"); F("use_custom_duration", target, "switch")
    gen_len = math("max(1, ceil((a-1)/4)*4+1)", "AUTO · VACE 생성 길이 = 4k+1 (≥ target)", (X[0], 1260), 1)
    L(target, 0, gen_len, "values.a")
    src_t = A("ImageFromBatch", "Source Frames → Target Length", (X[0], 1480), (430, 110), {"batch_index": 0, "length": 1}, color="video")
    L(vsrc, "images", src_t, "image"); L(target, 0, src_t, "length")

    # ---------------- 02 CANVAS
    ui_720 = A("PrimitiveBoolean", "UI · Canvas 720p", (X[1], 0), (430, 80), {"value": cfg["canvas_720p"]}, color="control")
    F("canvas_720p", ui_720, "value")
    budget = "(399360 + c*(921600-399360))"
    cw = math(f"max(16, floor(sqrt({budget}*a/max(b,1))/16)*16)", "AUTO · Canvas Width | 원본 비율 · 16px · 480p/720p 면적", (X[1], 130), 3)
    ch = math(f"max(16, floor(sqrt({budget}*b/max(a,1))/16)*16)", "AUTO · Canvas Height | 원본 비율 · 16px · 480p/720p 면적", (X[1], 350), 3)
    for m in (cw, ch):
        L(ssize, "width", m, "values.a"); L(ssize, "height", m, "values.b"); L(ui_720, 0, m, "values.c")
    src_c = resize("Source → Canvas (Lanczos · No Crop)", (X[1], 570), "lanczos", color="video")
    L(src_t, 0, src_c, "input"); L(cw, "INT", src_c, "resize_type.width"); L(ch, "INT", src_c, "resize_type.height")

    # ---------------- 03 MASK
    vmask = A("GetVideoComponents", "Mask Components", (X[2], 0), (430, 140), color="mask")
    F("mask_video", vmask, "video")
    msize = A("GetImageSize", "Mask Metadata | frames", (X[2], 200), (430, 130), color="mask")
    L(vmask, "images", msize, "image")
    m_t0 = A("ImageFromBatch", "Mask Frames ≤ Target", (X[2], 380), (430, 110), {"batch_index": 0, "length": 1}, color="mask")
    L(vmask, "images", m_t0, "image"); L(target, 0, m_t0, "length")
    m_c = resize("Mask → Canvas (Area · No Crop)", (X[2], 540), "area")
    L(m_t0, 0, m_c, "input"); L(cw, "INT", m_c, "resize_type.width"); L(ch, "INT", m_c, "resize_type.height")
    m_last = A("ImageFromBatch", "Mask Last Frame (hold)", (X[2], 750), (430, 110), {"batch_index": -1, "length": 1}, color="mask")
    L(m_c, 0, m_last, "image")
    pad_n = math("max(1, a-b)", "AUTO · Mask 부족 프레임 수 (짧은 마스크 = 마지막 프레임 유지)", (X[2], 910), 2)
    L(target, 0, pad_n, "values.a"); L(msize, "batch_size", pad_n, "values.b")
    m_rep = A("RepeatImageBatch", "Hold Last Mask Frame", (X[2], 1130), (430, 90), {"amount": 1}, color="mask")
    L(m_last, 0, m_rep, "image"); L(pad_n, "INT", m_rep, "amount")
    m_cat = A("ImageBatch", "Mask + Hold", (X[2], 1270), (430, 90), color="mask")
    L(m_c, 0, m_cat, "image1"); L(m_rep, 0, m_cat, "image2")
    m_full = A("ImageFromBatch", "Mask → Exact Target Frames", (X[2], 1410), (430, 110), {"batch_index": 0, "length": 1}, color="mask")
    L(m_cat, 0, m_full, "image"); L(target, 0, m_full, "length")

    m_raw = A("ImageToMask", "Mask Video → Mask (red · 흰색 포함)", (X[3], 0), (430, 90), {"channel": "red"}, color="mask")
    L(m_full, 0, m_raw, "image")
    m_invn = A("InvertMask", "Invert", (X[3], 140), (430, 70), color="mask")
    L(m_raw, 0, m_invn, "mask")
    m_inv = switch("MASK", "INVERT MODE | Mask or Inverted", (X[3], 260), color="mask")
    L(m_raw, 0, m_inv, "on_false"); L(m_invn, 0, m_inv, "on_true"); F("invert_mask", m_inv, "switch")
    m_bin = A("ThresholdMask", "Binarize 0.5 (압축 노이즈 제거)", (X[3], 440), (430, 90), {"value": 0.5}, color="mask")
    L(m_inv, 0, m_bin, "mask")
    m_grow = A("GrowMask", "Mask Expand (px)", (X[3], 580), (430, 110), {"expand": 0, "tapered_corners": True}, color="mask")
    L(m_bin, 0, m_grow, "mask"); F("mask_expand", m_grow, "expand")
    bw = math("a//8", "Block W = Canvas/8", (X[3], 740), 1, size=(430, 130))
    bh = math("a//8", "Block H = Canvas/8", (X[3], 910), 1, size=(430, 130))
    L(cw, "INT", bw, "values.a"); L(ch, "INT", bh, "values.a")
    m_down = resize("Block Align · ↓8 (Area)", (X[3], 1080), "area", mtype="MASK")
    L(m_grow, 0, m_down, "input"); L(bw, "INT", m_down, "resize_type.width"); L(bh, "INT", m_down, "resize_type.height")
    m_any = A("ThresholdMask", "Block Align · 어떤 픽셀이라도 → 블록 전체", (X[3], 1280), (430, 90), {"value": 0.001}, color="mask")
    L(m_down, 0, m_any, "mask")
    m_up = resize("Block Align · ↑8 (Nearest)", (X[3], 1420), "nearest-exact", mtype="MASK")
    L(m_any, 0, m_up, "input"); L(cw, "INT", m_up, "resize_type.width"); L(ch, "INT", m_up, "resize_type.height")
    m_fin = switch("MASK", "BLOCK ALIGN MODE | Mask or 8px Blocks", (X[3], 1630), color="mask")
    L(m_grow, 0, m_fin, "on_false"); L(m_up, 0, m_fin, "on_true"); F("mask_block_align", m_fin, "switch")

    gray_m = A("SolidMask", "VACE Gray 0.5 (MASK_COLOR 128)", (X[4], 0), (430, 130), {"value": 0.5, "width": 512, "height": 512}, color="mask")
    L(cw, "INT", gray_m, "width"); L(ch, "INT", gray_m, "height")
    gray = A("MaskToImage", "Gray Fill Image", (X[4], 180), (430, 70), color="mask")
    L(gray_m, 0, gray, "mask")
    control = A("ImageCompositeMasked", "CONTROL VIDEO | 마스크 영역 = Gray 0.5 · 나머지 = 원본", (X[4], 300), (430, 170),
                {"x": 0, "y": 0, "resize_source": False}, color="mask")
    L(src_c, 0, control, "destination"); L(gray, 0, control, "source"); L(m_fin, 0, control, "mask")

    # ---------------- 04 MODEL / PROMPT
    unet = A("UNETLoader", "Wan VACE Model", (X[5], 0), (430, 110), {"unet_name": cfg["unet"], "weight_dtype": "default"},
             color="model", properties=models_prop(cfg["unet"]))
    F("unet_name", unet, "unet_name")
    lora = A("LoraLoaderModelOnly", "Speed LoRA (CausVid)", (X[5], 160), (430, 120),
             {"lora_name": cfg["lora"], "strength_model": cfg["lora_strength"]}, color="model", properties=models_prop(cfg["lora"]))
    L(unet, 0, lora, "model"); F("lora_name", lora, "lora_name"); F("lora_strength", lora, "strength_model")
    msw = switch("MODEL", "TURBO | Base Model or + Speed LoRA", (X[5], 330), color="model")
    L(unet, 0, msw, "on_false"); L(lora, 0, msw, "on_true"); F("turbo", msw, "switch")
    shift = A("ModelSamplingSD3", "Model Shift 5", (X[5], 510), (430, 80), {"shift": 5.0}, color="sampling")
    L(msw, 0, shift, "model")
    clip = A("CLIPLoader", "UMT5 Text Encoder", (X[5], 640), (430, 130),
             {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}, color="model",
             properties=models_prop("umt5_xxl_fp8_e4m3fn_scaled.safetensors"))
    F("clip_name", clip, "clip_name")
    vae = A("VAELoader", "Wan VAE", (X[5], 820), (430, 80), {"vae_name": "wan_2.1_vae.safetensors"}, color="model",
            properties=models_prop("wan_2.1_vae.safetensors"))
    F("vae_name", vae, "vae_name")
    pos = A("CLIPTextEncode", "CLIP Text Encode (Positive Prompt)", (X[5], 950), (430, 200), {"text": cfg["positive"]}, color="input")
    L(clip, 0, pos, "clip"); F("positive_prompt", pos, "text")
    neg = A("CLIPTextEncode", "CLIP Text Encode (Negative Prompt)", (X[5], 1200), (430, 200), {"text": cfg["negative"]}, color="input")
    L(clip, 0, neg, "clip"); F("negative_prompt", neg, "text")

    st_n = A("PrimitiveInt", "INTERNAL · Steps (normal)", (X[6], 0), (430, 90), {"value": 20, "control_after_generate": "fixed"}, color="control")
    st_t = A("PrimitiveInt", f"INTERNAL · Steps (turbo · CausVid)", (X[6], 140), (430, 90),
             {"value": cfg["turbo_steps"], "control_after_generate": "fixed"}, color="control")
    steps = switch("INT", "TURBO | Steps", (X[6], 280))
    L(st_n, 0, steps, "on_false"); L(st_t, 0, steps, "on_true"); F("turbo", steps, "switch")
    cf_n = A("PrimitiveFloat", "INTERNAL · CFG (normal)", (X[6], 460), (430, 80), {"value": 6.0}, color="control")
    cf_t = A("PrimitiveFloat", "INTERNAL · CFG (turbo)", (X[6], 590), (430, 80), {"value": 1.0}, color="control")
    cfgsw = switch("FLOAT", "TURBO | CFG", (X[6], 720))
    L(cf_n, 0, cfgsw, "on_false"); L(cf_t, 0, cfgsw, "on_true"); F("turbo", cfgsw, "switch")

    # ---------------- 05 GENERATION
    vace = A("WanVaceToVideo", "Wan VACE | Auto Canvas · 4k+1 Length · Gray-fill Control", (X[7], 0), (430, 300),
             {"width": 832, "height": 480, "length": 81, "batch_size": 1, "strength": 1.0}, color="gen")
    L(pos, 0, vace, "positive"); L(neg, 0, vace, "negative"); L(vae, 0, vace, "vae")
    L(control, 0, vace, "control_video"); L(m_fin, 0, vace, "control_masks"); F("reference_image", vace, "reference_image")
    L(cw, "INT", vace, "width"); L(ch, "INT", vace, "height"); L(gen_len, "INT", vace, "length")
    F("vace_strength", vace, "strength")
    ks = A("KSampler", "KSampler", (X[7], 350), (430, 330),
           {"seed": cfg["seed"], "control_after_generate": "fixed", "steps": cfg["turbo_steps"], "cfg": 1.0,
            "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}, color="gen")
    L(shift, 0, ks, "model"); L(vace, "positive", ks, "positive"); L(vace, "negative", ks, "negative"); L(vace, "latent", ks, "latent_image")
    F("seed", ks, "seed"); F("seed_control", ks, "control_after_generate"); L(steps, 0, ks, "steps"); L(cfgsw, 0, ks, "cfg")
    trim = A("TrimVideoLatent", "Trim Reference Latent", (X[7], 730), (430, 80), {"trim_amount": 0}, color="gen")
    L(ks, 0, trim, "samples"); L(vace, "trim_latent", trim, "trim_amount")
    dec = A("VAEDecode", "Decode", (X[7], 860), (430, 70), color="video")
    L(trim, 0, dec, "samples"); L(vae, 0, dec, "vae")
    gen = A("ImageFromBatch", "FINAL TRIM | 4k+1 → Target Frames", (X[7], 980), (430, 110), {"batch_index": 0, "length": 1}, color="video")
    L(dec, 0, gen, "image"); L(target, 0, gen, "length")

    # ---------------- 06 OUTPUT SIZE / PIXEL LOCK
    ui_sc = A("PrimitiveFloat", "UI · Output Scale", (X[1], 800), (430, 80), {"value": cfg["output_scale"]}, color="control")
    F("output_scale", ui_sc, "value")
    ui_w = A("PrimitiveInt", "UI · Custom Width", (X[1], 930), (430, 90), {"value": 1920, "control_after_generate": "fixed"}, color="control")
    F("custom_width", ui_w, "value")
    ui_h = A("PrimitiveInt", "UI · Custom Height", (X[1], 1070), (430, 90), {"value": 1080, "control_after_generate": "fixed"}, color="control")
    F("custom_height", ui_h, "value")
    ow_s = math("max(2, round(a*b/2)*2)", "SOURCE × SCALE | Width (짝수)", (X[8], 0), 2)
    oh_s = math("max(2, round(a*b/2)*2)", "SOURCE × SCALE | Height (짝수)", (X[8], 200), 2)
    L(ssize, "width", ow_s, "values.a"); L(ui_sc, 0, ow_s, "values.b")
    L(ssize, "height", oh_s, "values.a"); L(ui_sc, 0, oh_s, "values.b")
    cw_e = math("max(2, round(a/2)*2)", "CUSTOM | Width (짝수)", (X[8], 400), 1)
    ch_e = math("max(2, round(a/2)*2)", "CUSTOM | Height (짝수)", (X[8], 600), 1)
    L(ui_w, 0, cw_e, "values.a"); L(ui_h, 0, ch_e, "values.a")
    ch_k = math("max(2, round(a*b/c/2)*2)", "KEEP ASPECT | custom W × source H / source W (짝수)", (X[8], 800), 3)
    L(ui_w, 0, ch_k, "values.a"); L(ssize, "height", ch_k, "values.b"); L(ssize, "width", ch_k, "values.c")
    ch_c = switch("INT", "KEEP ASPECT RATIO | Custom Height or Calculated", (X[8], 1020))
    L(ch_e, "INT", ch_c, "on_false"); L(ch_k, "INT", ch_c, "on_true"); F("keep_aspect_ratio", ch_c, "switch")
    ow = switch("INT", "RESOLUTION MODE | Width", (X[8], 1200))
    L(ow_s, "INT", ow, "on_false"); L(cw_e, "INT", ow, "on_true"); F("use_custom_resolution", ow, "switch")
    oh = switch("INT", "RESOLUTION MODE | Height", (X[8], 1380))
    L(oh_s, "INT", oh, "on_false"); L(ch_c, 0, oh, "on_true"); F("use_custom_resolution", oh, "switch")

    X9, X10 = X[8] + 470, X[8] + 940
    gen_o = resize("Generated → Output Size (Lanczos · No Crop)", (X9, 0), "lanczos", color="output")
    L(gen, 0, gen_o, "input"); L(ow, 0, gen_o, "resize_type.width"); L(oh, 0, gen_o, "resize_type.height")
    raw_o = resize("Raw Source → Output Size (Pixel-Lock Destination)", (X9, 210), "lanczos", color="output")
    L(src_t, 0, raw_o, "input"); L(ow, 0, raw_o, "resize_type.width"); L(oh, 0, raw_o, "resize_type.height")
    m_o = resize("Mask → Output Size (Bilinear edge)", (X9, 420), "bilinear", mtype="MASK", color="output")
    L(m_fin, 0, m_o, "input"); L(ow, 0, m_o, "resize_type.width"); L(oh, 0, m_o, "resize_type.height")
    lock = A("ImageCompositeMasked", "PIXEL LOCK | VACE Inside · Raw Source Outside", (X9, 630), (430, 170),
             {"x": 0, "y": 0, "resize_source": False}, color="output")
    L(raw_o, 0, lock, "destination"); L(gen_o, 0, lock, "source"); L(m_o, 0, lock, "mask")
    fin = switch("IMAGE", "PIXEL LOCK MODE | Generated or Locked", (X9, 850), color="output")
    L(gen_o, 0, fin, "on_false"); L(lock, 0, fin, "on_true"); F("pixel_lock", fin, "switch")
    vid = A("CreateVideo", "Create Final Video — Source FPS · Audio · Length", (X10, 0), (430, 140), {"fps": 30.0}, color="output")
    L(fin, 0, vid, "images"); L(fps_sel, 0, vid, "fps"); L(vsrc, "audio", vid, "audio")
    prev = A("CreateVideo", "Control / Mask Preview Video", (X10, 200), (430, 140), {"fps": 30.0}, color="output")
    L(control, 0, prev, "images"); L(fps_sel, 0, prev, "fps")
    sg.to_output("video", vid, 0)
    sg.to_output("control_preview", prev, 0)

    by = {n["id"]: n for n in sg.nodes}
    sg.group("01 SOURCE · LENGTH · FPS", [vsrc, ssize, ui_fps, fps_sel, ui_dur, cust_len, target, gen_len, src_t], "#0A5F9E")
    sg.group("02 AUTO CANVAS · 16px · 480p/720p 면적", [ui_720, cw, ch, src_c, ui_sc, ui_w, ui_h], "#0A5F9E")
    sg.group("03 MASK · 길이 맞춤 · Invert · Expand · Block · Gray Control",
             [vmask, msize, m_t0, m_c, m_last, pad_n, m_rep, m_cat, m_full, m_raw, m_invn, m_inv, m_bin, m_grow, bw, bh,
              m_down, m_any, m_up, m_fin, gray_m, gray, control], "#08765F")
    sg.group("04 MODEL · PROMPT", [unet, lora, msw, shift, clip, vae, pos, neg, st_n, st_t, steps, cf_n, cf_t, cfgsw], "#48538E")
    sg.group("05 GENERATION", [vace, ks, trim, dec, gen], "#9A2854")
    sg.group("06 OUTPUT SIZE · PIXEL LOCK · VIDEO", [ow_s, oh_s, cw_e, ch_e, ch_k, ch_c, ow, oh, gen_o, raw_o, m_o, lock, fin, vid, prev], "#2C7736")
    return sg


def add_note(g, title, text, pos, size):
    n = {"id": g._nid(), "type": "MarkdownNote", "pos": list(pos), "size": list(size), "flags": {}, "order": 0, "mode": 0,
         "inputs": [], "outputs": [], "title": title, "properties": {}, "widgets_values": [text],
         "widgets_values_named": {"text": text}, "color": COLORS["note"][0], "bgcolor": COLORS["note"][1]}
    g.nodes.append(n)
    g.byid[n["id"]] = n
    return n


def build(cfg):
    ids = {"node": 1000, "link": 2000}
    top = Graph(ids)
    main = build_main(ids, cfg)

    src = top.add("LoadVideo", "1. Source Video | 원본 Resolution·FPS·Frame Count·Audio 자동 읽기", (-2700, -940), (480, 700),
                  {"file": cfg["src_file"]}, color="input")
    msk = top.add("LoadVideo", "2. Mask Video | 흰색·빨강 = 생성 영역 / 검정 = 원본 유지", (-2180, -940), (480, 700),
                  {"file": cfg["mask_file"]}, color="input")
    ref = top.add("LoadImage", "3. Reference Image (선택 · 안 쓰면 Bypass)", (-2700, -180), (480, 560),
                  {"image": cfg["ref_file"]}, color="input")
    mc = main.instance(top, "4. MAIN CONTROL | Wan VACE — Creator UI", (-1620, -940), (600, 1260))
    save = top.add("SaveVideo", "5. Final Output | 원본 FPS·오디오·길이 유지", (-960, -940), (620, 900),
                   {"filename_prefix": cfg["prefix"], "format": "auto", "codec": "auto"}, color="output")
    prev = top.add("SaveVideo", "(선택) Control / Mask Preview | Gray = 생성 영역", (-960, 20), (620, 560),
                   {"filename_prefix": cfg["prefix"] + "_control", "format": "auto", "codec": "auto"}, color="output")

    # optional result/source comparison (Video Stitch subgraph reused from the Animate2 file)
    stitch_def = copy.deepcopy(STITCH)
    stitch_def["inputs"][0]["label"] = "Result (left)"
    stitch_def["inputs"][1]["label"] = "Source (right)"
    stitch = {"id": top._nid(), "type": stitch_def["id"], "pos": [-300, -940], "size": [290, 160], "flags": {}, "order": 0, "mode": 0,
              "inputs": [{"label": "Result (left)", "name": "video", "type": "VIDEO", "link": None},
                         {"label": "Source (right)", "name": "video_1", "type": "VIDEO", "link": None}],
              "outputs": [{"name": "VIDEO", "type": "VIDEO", "links": []}],
              "title": "(선택) 결과 / 원본 비교", "properties": {"cnr_id": "comfy-core", "previewExposures": [], "ver": "0.13.0"},
              "widgets_values": ["right", True, 0, "white"],
              "widgets_values_named": {"direction": "right", "match_image_size": True, "spacing_width": 0, "spacing_color": "white"},
              "color": "#956500", "bgcolor": "#493200"}
    top.nodes.append(stitch); top.byid[stitch["id"]] = stitch
    cmp_save = top.add("SaveVideo", "(선택) 결과 / 원본 비교 저장", (40, -940), (760, 700),
                       {"filename_prefix": cfg["prefix"] + "_compare", "format": "auto", "codec": "auto"}, color="output")

    top.link(src, 0, mc, "source_video")
    top.link(msk, 0, mc, "mask_video")
    top.link(ref, "IMAGE", mc, "reference_image")
    top.link(mc, "video", save, "video")
    top.link(mc, "control_preview", prev, "video")
    top.link(save, 0, stitch, "video")
    top.link(src, 0, stitch, "video_1")
    top.link(stitch, 0, cmp_save, "video")

    n1 = add_note(top, cfg["guide_title"], cfg["guide"], (-1560, 460), (700, 1500))
    n2 = add_note(top, "모델 설치 — 클릭 다운로드", cfg["models_md"], (-2400, 460), (800, 1500))
    n3 = add_note(top, "자동 확장 — 연결 구조", cfg["structure_md"], (-820, 700), (820, 1100))

    top.group("01 INPUT", [src, msk, ref], "#0A5F9E")
    top.group("MAIN CONTROL", [mc], "#8B610B")
    top.group("OUTPUT (Preview / 비교는 선택)", [save, prev, stitch, cmp_save], "#2C7736")
    top.group("안내 / 모델 다운로드", [n1, n2, n3], "#67318E")

    stitch_ids = [n["id"] for n in stitch_def["nodes"]] + [l["id"] for l in stitch_def["links"]]
    assert max(stitch_ids) < 1000, "stitch ids must not collide"
    wf = {
        "id": sid("workflow", cfg["out"]), "revision": 0,
        "last_node_id": ids["node"], "last_link_id": ids["link"],
        "nodes": top.nodes, "links": top_links(top), "groups": top.groups,
        "definitions": {"subgraphs": [stitch_def, main.definition()]},
        "config": {},
        "extra": {
            "ds": {"scale": 0.55, "offset": [2900, 1100]},
            "frontendVersion": "1.48.7",
            "workflowRendererVersion": "LG",
            "creator_ui_audit": cfg["audit"],
        },
        "version": 0.4,
    }
    for s in wf["definitions"]["subgraphs"]:
        s["state"]["lastNodeId"] = ids["node"]
        s["state"]["lastLinkId"] = ids["link"]
    return wf


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import vace_configs
    for key, cfg in vace_configs.CONFIGS.items():
        wf = build(cfg)
        json.dump(wf, open(os.path.join(OUT, cfg["out"]), "w"), ensure_ascii=False, indent=2)
        print("wrote", cfg["out"], len(wf["nodes"]), "top nodes,", len(wf["definitions"]["subgraphs"][1]["nodes"]), "main nodes")
