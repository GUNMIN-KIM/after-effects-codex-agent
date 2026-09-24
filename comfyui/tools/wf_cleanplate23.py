"""Clean Plate on the LTX-2.3 engine (Comfy Cloud: the 2.3 Clean Plate LoRA does not work on the 2.5 transformer)."""
import sys
from builder import G, build

g = G()

def math(expr, title, pos, *srcs):
    n = g.node("ComfyMathExpression", title, pos, {"expression": expr}, kind="param", size=[300, 110])
    for i, s in enumerate(srcs):
        g.link(s, n, "values." + "abcde"[i])
    return n

# ─────────────── 조작 패널 ───────────────
vid = g.node("VHS_LoadVideo", "① 입력 영상 (fps·해상도 그대로)", (0, 0),
             {"video": "test.mp4", "force_rate": 0, "frame_load_cap": 0, "format": "None"}, kind="input", size=[420, 600])
prompt = g.node("PrimitiveStringMultiline", "② 사람이 없는 빈 장면 설명 (영어 권장)", (0, 660),
                {"value": "An empty street scene with no people and no vehicles. The same buildings, ground, road markings, signs, shop fronts, lighting, shadows and camera motion as the source video. Static environment only."},
                kind="input", size=[420, 180])
neg = g.node("PrimitiveStringMultiline", "negative", (0, 860),
             {"value": "person, people, human, figure, limb, arm, hand, leg, body part, backpack, shadow of a person, leftover people, leftover figures, ghosting, semi-transparent remnants, blurry, soft, distorted, inconsistent motion, jitter, color shift, worst quality, cartoon, video game, ugly, floating objects"},
             kind="input", size=[420, 160])
cap = g.node("PrimitiveInt", "③ 최대 프레임 (0=전체 · VRAM 부족하면 121)", (460, 0), {"value": 0}, kind="param")
g.link(cap, vid, "frame_load_cap")
maxl = g.node("PrimitiveInt", "④ 생성 해상도 긴 변 상한 (기존 2.3 워크플로처럼 원본 해상도 · 1920)", (460, 110), {"value": 1920}, kind="param")
seed = g.node("PrimitiveInt", "⑤ seed", (460, 220), {"value": 42}, kind="param")
lora_s = g.node("PrimitiveFloat", "⑥ Clean Plate LoRA 강도", (460, 330), {"value": 1.0}, kind="param")
cm_s = g.node("PrimitiveFloat", "⑦ 원본 색 일치 강도 (0=끔)", (460, 440), {"value": 0.5}, kind="param")
keep_audio = g.node("PrimitiveBoolean", "⑧ 원본 오디오 포함 (기본 무음)", (460, 550), {"value": False}, kind="param")
g.group("조작 패널 — 여기만 만지면 됩니다", (-30, -60, 950, 1120), "#48538E", main=True)

# ─────────────── 모델 ───────────────
XM = 1000
ckpt = g.node("CheckpointLoaderSimple", "LTX 2.3 dev FP8 (기존 클라우드 파일)", (XM, 0),
              {"ckpt_name": "ltx-2.3-22b-dev-fp8.safetensors"}, kind="model")
dlora = g.node("LoraLoaderModelOnly", "2.3 Distilled LoRA 0.6 (기존 값)", (XM, 140),
               {"lora_name": "ltx-2.3-22b-distilled-lora-384-1.1.safetensors", "strength_model": 0.6}, kind="model")
g.link(ckpt, dlora, "model")
ic = g.node("LTXICLoRALoaderModelOnly", "Clean Plate IC-LoRA 2.3", (XM, 300),
            {"lora_name": "ltx-2.3-22b-ic-lora-clean-plate-1.0.safetensors"}, kind="model")
g.link(dlora, ic, "model"); g.link(lora_s, ic, "strength_model")
clip = g.node("DualCLIPLoader", "Gemma 3 12B + LTX 2.3 projection", (XM, 460),
              {"clip_name1": "gemma_3_12B_it_fp4_mixed.safetensors", "clip_name2": "ltx-2.3_text_projection_bf16.safetensors", "type": "ltxv"}, kind="model")
vae = g.node("VAELoaderKJ", "LTX 2.3 Video VAE", (XM, 640), {"vae_name": "LTX23_video_vae_bf16.safetensors", "device": "main_device", "weight_dtype": "bf16"}, kind="model")
avae = g.node("VAELoaderKJ", "LTX 2.3 Audio VAE", (XM, 800), {"vae_name": "LTX23_audio_vae_bf16.safetensors", "device": "main_device", "weight_dtype": "bf16"}, kind="model")
g.group("모델 (기존 클라우드 2.3 파일)", (XM - 30, -60, 400, 1000), "#5E258B", main=True)

MAIN_UPTO = len(g.nodes)
# ─────────────── 자동 계산 ───────────────
XA = XM + 440
info = g.node("VHS_VideoInfo", "원본 fps", (XA, 0), {}, kind="post")
g.link(vid[3], info, "video_info")
fps = info[5]
sz = g.node("GetImageSize", "원본 크기·프레임 수", (XA, 260), {}, kind="post")
g.link(vid[0], sz, "image")
W0, H0, N = sz[0], sz[1], sz[2]
Wf = math("max(32, round(a*min(1, c/max(a,b))/32)*32)", "생성 가로 (32배수)", (XA, 400), W0, H0, maxl[0])
Hf = math("max(32, round(b*min(1, c/max(a,b))/32)*32)", "생성 세로 (32배수)", (XA, 540), W0, H0, maxl[0])
Wh, Hh = Wf, Hf
M = math("a + (8 - (a-1) % 8) % 8", "LTX 프레임 수 (8n+1)", (XA + 340, 0), N)
LAST = math("a-1", "마지막 프레임 번호", (XA + 340, 140), N)
g.group("자동 계산", (XA - 30, -60, 720, 1000), "#414B8F")

# ─────────────── 입력 준비 ───────────────
XP = XA + 760
lastf = g.node("ImageFromBatch", "마지막 프레임", (XP, 0), {}, kind="guide")
g.link(vid[0], lastf, "image"); g.link(LAST["INT"], lastf, "batch_index")
rep = g.node("RepeatImageBatch", "마지막 프레임 ×8", (XP, 140), {"amount": 8}, kind="guide")
g.link(lastf, rep, "image")
cat = g.node("BatchImagesNode", "원본 + 패딩", (XP, 260), {}, kind="guide")
g.link(vid[0], cat, "images.image0"); g.link(rep, cat, "images.image1")
fM = g.node("ImageFromBatch", "8n+1 프레임", (XP, 380), {}, kind="guide")
g.link(cat, fM, "image"); g.link(M["INT"], fM, "length")
gimg = g.node("ImageScale", "IC-LoRA 레퍼런스 (생성 해상도)", (XP, 520), {"upscale_method": "lanczos", "crop": "disabled"}, kind="guide")
g.link(fM, gimg, "image"); g.link(Wh["INT"], gimg, "width"); g.link(Hh["INT"], gimg, "height")
g.group("입력 준비", (XP - 30, -60, 400, 760), "#6B4500")

# ─────────────── Stage 1 ───────────────
XS = XP + 440
pe = g.node("CLIPTextEncode", "positive", (XS, 0), {}, kind="gen")
g.link(clip, pe, "clip"); g.link(prompt, pe, "text")
ne = g.node("CLIPTextEncode", "negative", (XS, 120), {}, kind="gen")
g.link(clip, ne, "clip"); g.link(neg, ne, "text")
cond = g.node("LTXVConditioning", "원본 fps", (XS, 240), {}, kind="gen")
g.link(pe, cond, "positive"); g.link(ne, cond, "negative"); g.link(fps, cond, "frame_rate")
e1 = g.node("EmptyLTXVLatentVideo", "생성 latent", (XS, 380), {}, kind="gen")
g.link(Wh["INT"], e1, "width"); g.link(Hh["INT"], e1, "height"); g.link(M["INT"], e1, "length")
gd = g.node("LTXAddVideoICLoRAGuide", "원본 영상 → Clean Plate 가이드", (XS, 540),
            {"frame_idx": 0, "strength": 1.0, "crop": "disabled", "use_tiled_encode": False}, kind="guide")
g.link(cond[0], gd, "positive"); g.link(cond[1], gd, "negative"); g.link(vae, gd, "vae"); g.link(e1, gd, "latent")
g.link(gimg, gd, "image"); g.link(ic[1], gd, "latent_downscale_factor")
ea = g.node("LTXVEmptyLatentAudio", "오디오 latent", (XS, 860), {}, kind="gen")
g.link(avae, ea, "audio_vae"); g.link(M["INT"], ea, "frames_number"); g.link(fps, ea, "frame_rate")
av1 = g.node("LTXVConcatAVLatent", "AV latent", (XS, 1000), {}, kind="gen")
g.link(gd[2], av1, "video_latent"); g.link(ea, av1, "audio_latent")
cg1 = g.node("CFGGuider", "cfg 1", (XS + 340, 0), {"cfg": 1.0}, kind="gen")
g.link(ic, cg1, "model"); g.link(gd[0], cg1, "positive"); g.link(gd[1], cg1, "negative")
nz = g.node("RandomNoise", "noise", (XS + 340, 120), {}, kind="gen")
g.link(seed, nz, "noise_seed")
k1 = g.node("KSamplerSelect", "euler_ancestral_cfg_pp (기존 2.3 값)", (XS + 340, 240), {"sampler_name": "euler_ancestral_cfg_pp"}, kind="gen")
s1s = g.node("ManualSigmas", "distilled 8-step", (XS + 340, 340), {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}, kind="gen")
s1 = g.node("SamplerCustomAdvanced", "사람 제거 · 1-stage (기존 2.3 구조)", (XS + 340, 460), {}, kind="gen")
g.link(nz, s1, "noise"); g.link(cg1, s1, "guider"); g.link(k1, s1, "sampler"); g.link(s1s, s1, "sigmas"); g.link(av1, s1, "latent_image")
sep1 = g.node("LTXVSeparateAVLatent", "분리", (XS + 340, 620), {}, kind="gen")
g.link(s1[0], sep1, "av_latent")
crop = g.node("LTXVCropGuides", "가이드 토큰 제거", (XS + 340, 730), {}, kind="gen")
g.link(gd[0], crop, "positive"); g.link(gd[1], crop, "negative"); g.link(sep1[0], crop, "latent")
g.group("생성 — 2.3 IC-LoRA 8 step", (XS - 30, -60, 720, 1200), "#9A1F50")

dec = g.node("VAEDecodeTiled", "디코드", (XS + 340, 860), {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}, kind="gen")
g.link(crop[2], dec, "samples"); g.link(vae, dec, "vae")
X2 = XS + 320

# ─────────────── 후처리 ───────────────
XF = X2 + 440
rs = g.node("ImageScale", "원본 해상도로 정확히 복원", (XF, 0), {"upscale_method": "lanczos", "crop": "disabled"}, kind="post")
g.link(dec, rs, "image"); g.link(W0, rs, "width"); g.link(H0, rs, "height")
trim = g.node("ImageFromBatch", "원래 프레임 수", (XF, 180), {}, kind="post")
g.link(rs, trim, "image"); g.link(N, trim, "length")
cmn = g.node("ColorMatchV2", "원본 프레임별 색 일치 (색 털림 방지)", (XF, 320), {"method": "mkl"}, kind="color")
g.link(trim, cmn, "image_target"); g.link(vid[0], cmn, "image_ref"); g.link(cm_s, cmn, "strength")
asw = g.node("ComfySwitchNode", "⑧ 오디오", (XF, 520), {}, kind="param")
g.link(vid[2], asw, "on_true"); g.link(keep_audio, asw, "switch")
g.group("후처리", (XF - 30, -60, 400, 720), "#006F89")

XO = XF + 440
out = g.node("VHS_VideoCombine", "⑨ Clean Plate MP4", (XO, 0),
             {"filename_prefix": "LTX2.3_CleanPlate/cleanplate", "format": "video/h264-mp4", "crf": 10}, kind="out", size=[460, 560])
g.link(cmn, out, "images"); g.link(asw, out, "audio"); g.link(fps, out, "frame_rate")
g.group("출력", (2070, -60, 520, 660), "#287A32", main=True)

g.note("사용법 · 원리", """# Clean Plate — LTX 2.3 엔진 (Comfy Cloud용)

## 왜 2.3인가
- 2.5 트랜스포머 + 2.3 Clean Plate LoRA 조합은 **회색 화면**이 나왔다. Clean Plate는 Lightricks가 2.5용을 따로 다시 학습해 낸 LoRA라, 2.3판은 2.5에서 동작하지 않는다 (In/Outpaint·Union 2.3 LoRA는 공식 2.5 예제가 그대로 쓰는 것과 다름)
- Comfy Cloud에는 2.5 Clean Plate LoRA가 없으므로, 기존에 쓰던 **2.3 엔진**(dev FP8 + distilled LoRA 0.6 + 2.3 Clean Plate LoRA, Gemma 3)을 그대로 쓴다
- 2.5 LoRA가 있는 환경은 `LTX2.5_CleanPlate.json` 사용

## 기존 2.3 워크플로 대비 개선
- VHS `LTXV` 포맷(해상도·프레임 강제 자르기) 제거 → 원본 해상도·프레임 수 그대로
- 프레임 수 8n+1 자동 패딩 후 원래 길이로 복원
- 원본 fps 자동, controlaltai `TwoWaySwitch` 의존 제거
- ⑦ 결과를 원본 프레임별 색에 맞춤 (사람이 화면 대부분이면 0.2 이하)
- 메인 그래프(조작·모델·출력) + CORE 서브그래프

## 팁
- 사람이 남으면 ⑥ 1.1~1.2, 배경이 뭉개지면 0.8~0.9
- ② 프롬프트는 "사람 없는 같은 장면"을 설명 (지울 대상 이름을 쓰지 말 것)
- VRAM 부족하면 ③ 프레임 수를 줄이거나 ④를 1280으로
""", (0, 1080), size=[900, 560])

note_key = g.nodes[-1]["key"]  # 사용법 노트
g.core("LTX 2.3 CLEANPLATE CORE", "LTX 2.3 CLEANPLATE CORE  (더블클릭=내부 진입)", (1440, 0),
       [n["key"] for n in g.nodes[:MAIN_UPTO]] + [out, note_key],
       relocate={out: (2100, 0)}, color="gen",
       out_labels={"원본 fps": "fps", "⑦ 소리 없으면 무음 출력": "최종 오디오", "⑥ 원본 오디오 그대로": "최종 오디오", "⑧ 오디오": "최종 오디오", "원본 + 연장 (이음새 크로스페이드)": "최종 영상 (원본+연장)"})

build(g, sys.argv[1] if len(sys.argv) > 1 else "/opt/cf/out_cleanplate23.json")
