"""LTX-2.5 video outpaint: official two-stage IC-LoRA graph + original 1:1 pixel restore via Laplacian blend."""
import sys
from builder import G, build

g = G()

def math(expr, title, pos, *srcs):
    n = g.node("ComfyMathExpression", title, pos, {"expression": expr}, kind="param", size=[300, 110])
    for i, s in enumerate(srcs):
        g.link(s, n, "values." + "abcde"[i])
    return n

# ─────────────── 조작 패널 ───────────────
vid = g.node("VHS_LoadVideo", "① 입력 영상 (fps 유지)", (0, 0),
             {"video": "test.mp4", "force_rate": 0, "frame_load_cap": 121, "format": "None"}, kind="input", size=[420, 600])
ar = g.node("ResolutionSelector", "② 확장할 화면비 (캔버스 크기는 원본 기준 자동)", (460, 0),
            {"aspect_ratio": "21:9 (Ultrawide)", "megapixels": 1.0, "multiple": 32}, kind="param")
prompt = g.node("PrimitiveStringMultiline", "③ 바깥 영역 설명 (비워도 됨 · 채울 배경을 쓰면 더 정확)", (0, 660),
                {"value": ""}, kind="input", size=[420, 180])
neg = g.node("PrimitiveStringMultiline", "negative", (0, 860),
             {"value": "pc game, console game, video game, cartoon, childish, ugly, visible seam, border, frame, black bars, letterbox, color shift, mismatched lighting, duplicated objects, distorted faces"},
             kind="input", size=[420, 140])
maxl = g.node("PrimitiveInt", "④ 생성 해상도 긴 변 상한 (VRAM 부족하면 1536)", (460, 260), {"value": 1920}, kind="param")
seed = g.node("PrimitiveInt", "⑤ seed", (460, 370), {"value": 42}, kind="param")
has_audio = g.node("PrimitiveBoolean", "⑥ 원본에 소리가 있음 (무음이면 끄기)", (460, 480), {"value": True}, kind="param")
lora_s = g.node("PrimitiveFloat", "⑦ Outpaint IC-LoRA 강도", (460, 590), {"value": 1.0}, kind="param")
cm_s = g.node("PrimitiveFloat", "⑧ 생성 영역 색 보정 강도 (원본 기준 · 0=끔)", (460, 700), {"value": 1.0}, kind="param")
dil = g.node("PrimitiveInt", "⑨ 최종 경계 블렌드 확장 (0=원본 픽셀 최대 보존 · 선 보이면 2~4)", (460, 810), {"value": 0}, kind="param")
g.group("조작 패널 — 여기만 만지면 됩니다", (-30, -60, 950, 1100), "#48538E", main=True)

# ─────────────── 모델 ───────────────
XM = 1000
unet = g.node("UNETLoader", "LTX-2.5 distilled (int8)", (XM, 0),
              {"unet_name": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"}, kind="model")
ic = g.node("LTXICLoRALoaderModelOnly", "In/Outpaint IC-LoRA (Lightricks 공식 2.5 그래프와 동일 · 2.3 파일)", (XM, 140),
            {"lora_name": "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors"}, kind="model")
g.link(unet, ic, "model"); g.link(lora_s, ic, "strength_model")
clip = g.node("CLIPLoader", "Gemma 4 12B + LTX-2.5 projection", (XM, 300),
              {"clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "type": "ltxv"}, kind="model")
vae = g.node("VAELoader", "LTX-2.5 Video VAE", (XM, 440), {"vae_name": "ltx-2.5-video-vae-bf16.safetensors"}, kind="model")
avae = g.node("VAELoader", "LTX-2.5 Audio VAE", (XM, 540), {"vae_name": "ltx-2.5-audio-vae-bf16.safetensors"}, kind="model")
g.group("모델", (XM - 30, -60, 400, 720), "#5E258B", main=True)

MAIN_UPTO = len(g.nodes)
# ─────────────── 자동 계산 ───────────────
XA = XM + 440
info = g.node("VHS_VideoInfo", "원본 fps", (XA, 0), {}, kind="post")
g.link(vid[3], info, "video_info")
fps = info[5]
sz = g.node("GetImageSize", "원본 크기·프레임 수", (XA, 260), {}, kind="post")
g.link(vid[0], sz, "image")
W0, H0, N = sz[0], sz[1], sz[2]
Wc = math("ceil(max(a, b*c/d)/64)*64", "최종 캔버스 가로 (원본 1:1 수용)", (XA, 400), W0, H0, ar[0], ar[1])
Hc = math("ceil(max(b, a*d/c)/64)*64", "최종 캔버스 세로 (원본 1:1 수용)", (XA, 540), W0, H0, ar[0], ar[1])
Wg = math("max(64, round(a*min(1, c/max(a,b))/64)*64)", "stage2 생성 가로", (XA, 680), Wc["INT"], Hc["INT"], maxl[0])
Hg = math("max(64, round(b*min(1, c/max(a,b))/64)*64)", "stage2 생성 세로", (XA, 820), Wc["INT"], Hc["INT"], maxl[0])
Wh = math("a//2", "stage1 가로", (XA + 340, 0), Wg["INT"])
Hh = math("a//2", "stage1 세로", (XA + 340, 140), Hg["INT"])
M = math("a + (8 - (a-1) % 8) % 8", "LTX 프레임 수 (8n+1로 올림)", (XA + 340, 280), N)
LAST = math("a-1", "마지막 프레임 번호", (XA + 340, 420), N)
PX = math("(a-b)//2", "원본 X 위치", (XA + 340, 560), Wc["INT"], W0)
PY = math("(a-b)//2", "원본 Y 위치", (XA + 340, 700), Hc["INT"], H0)
g.group("자동 계산", (XA - 30, -60, 720, 1060), "#414B8F")

# ─────────────── 입력 준비 ───────────────
XP = XA + 760
lastf = g.node("ImageFromBatch", "마지막 프레임", (XP, 0), {}, kind="guide")
g.link(vid[0], lastf, "image"); g.link(LAST["INT"], lastf, "batch_index")
rep = g.node("RepeatImageBatch", "마지막 프레임 ×8", (XP, 140), {"amount": 8}, kind="guide")
g.link(lastf, rep, "image")
cat = g.node("BatchImagesNode", "원본 + 패딩", (XP, 260), {}, kind="guide")
g.link(vid[0], cat, "images.image0"); g.link(rep, cat, "images.image1")
fM = g.node("ImageFromBatch", "8n+1 프레임으로 자르기", (XP, 380), {}, kind="guide")
g.link(cat, fM, "image"); g.link(M["INT"], fM, "length")
pad = g.node("ImagePadForOutpaintTargetSize", "원본 1:1 중앙 배치 + 바깥 마스크", (XP, 520),
             {"feathering": 0, "upscale_method": "lanczos"}, kind="guide")
g.link(fM, pad, "image"); g.link(Wc["INT"], pad, "target_width"); g.link(Hc["INT"], pad, "target_height")
ref2 = g.node("ImageScale", "stage2 해상도 레퍼런스", (XP, 720), {"upscale_method": "lanczos", "crop": "disabled"}, kind="guide")
g.link(pad[0], ref2, "image"); g.link(Wg["INT"], ref2, "width"); g.link(Hg["INT"], ref2, "height")
ref1 = g.node("ImageScale", "stage1 해상도 레퍼런스", (XP, 900), {"upscale_method": "area", "crop": "disabled"}, kind="guide")
g.link(pad[0], ref1, "image"); g.link(Wh["INT"], ref1, "width"); g.link(Hh["INT"], ref1, "height")
m1i = g.node("MaskToImage", "마스크→이미지", (XP, 1080), {}, kind="guide", collapsed=True)
g.link(pad[1], m1i, "mask")
m1s = g.node("ImageScale", "stage1 마스크 크기", (XP, 1120), {"upscale_method": "area", "crop": "disabled"}, kind="guide", collapsed=True)
g.link(m1i, m1s, "image"); g.link(Wh["INT"], m1s, "width"); g.link(Hh["INT"], m1s, "height")
m1 = g.node("ImageToMask", "stage1 마스크", (XP, 1160), {"channel": "red"}, kind="guide", collapsed=True)
g.link(m1s, m1, "image")
spm_i = g.node("MaskToImage", "마스크→이미지", (XP + 200, 1080), {}, kind="guide", collapsed=True)
g.link(pad[1], spm_i, "mask")
spm_f = g.node("ImageFromBatch", "첫 프레임 마스크", (XP + 200, 1120), {"batch_index": 0, "length": 1}, kind="guide", collapsed=True)
g.link(spm_i, spm_f, "image")
spm = g.node("ImageToMask", "공간 마스크 (흰색=바깥=생성)", (XP + 200, 1160), {"channel": "red"}, kind="guide", collapsed=True)
g.link(spm_f, spm, "image")
green1 = g.node("LTXVInpaintPreprocess", "바깥 영역 → 초록 신호 (IC-LoRA 입력)", (XP, 1260), {}, kind="guide")
g.link(ref1, green1, "images"); g.link(m1, green1, "mask")
g.group("입력 준비 — 공식 Outpaint 전처리", (XP - 30, -60, 400, 1440), "#6B4500")

# ─────────────── Stage 1 ───────────────
XS = XP + 440
pe = g.node("CLIPTextEncode", "positive", (XS, 0), {}, kind="gen")
g.link(clip, pe, "clip"); g.link(prompt, pe, "text")
ne = g.node("CLIPTextEncode", "negative", (XS, 120), {}, kind="gen")
g.link(clip, ne, "clip"); g.link(neg, ne, "text")
cond = g.node("LTXVConditioning", "원본 fps", (XS, 240), {}, kind="gen")
g.link(pe, cond, "positive"); g.link(ne, cond, "negative"); g.link(fps, cond, "frame_rate")
e1 = g.node("EmptyLTXVLatentVideo", "stage1 latent", (XS, 380), {}, kind="gen")
g.link(Wh["INT"], e1, "width"); g.link(Hh["INT"], e1, "height"); g.link(M["INT"], e1, "length")
gd = g.node("LTXAddVideoICLoRAGuideAdvanced", "Outpaint 가이드 (원본 영상 + 초록 마스크)", (XS, 540),
            {"frame_idx": 0, "strength": 1.0, "crop": "disabled", "use_tiled_encode": False, "attention_strength": 1.0}, kind="guide")
g.link(cond[0], gd, "positive"); g.link(cond[1], gd, "negative"); g.link(vae, gd, "vae"); g.link(e1, gd, "latent")
g.link(green1, gd, "image"); g.link(ic[1], gd, "latent_downscale_factor")
aenc = g.node("VAEEncodeAudio", "원본 오디오 인코드", (XS, 900), {}, kind="gen")
g.link(vid[2], aenc, "audio"); g.link(avae, aenc, "vae")
aref = g.node("LTXVSetAudioRefTokens", "원본 오디오 고정 (립싱크·동기 유지)", (XS, 1020), {}, kind="gen")
g.link(gd[0], aref, "positive"); g.link(gd[1], aref, "negative"); g.link(aenc, aref, "audio_latent")
ea = g.node("LTXVEmptyLatentAudio", "무음 영상용 빈 오디오", (XS, 1160), {}, kind="gen")
g.link(avae, ea, "audio_vae"); g.link(M["INT"], ea, "frames_number"); g.link(fps, ea, "frame_rate")
sp = g.node("ComfySwitchNode", "⑥ positive", (XS + 340, 0), {}, kind="param")
g.link(gd[0], sp, "on_false"); g.link(aref[0], sp, "on_true"); g.link(has_audio, sp, "switch")
sn = g.node("ComfySwitchNode", "⑥ negative", (XS + 340, 110), {}, kind="param")
g.link(gd[1], sn, "on_false"); g.link(aref[1], sn, "on_true"); g.link(has_audio, sn, "switch")
sa = g.node("ComfySwitchNode", "⑥ audio latent", (XS + 340, 220), {}, kind="param")
g.link(ea, sa, "on_false"); g.link(aref[2], sa, "on_true"); g.link(has_audio, sa, "switch")
av1 = g.node("LTXVConcatAVLatent", "AV latent", (XS + 340, 330), {}, kind="gen")
g.link(gd[2], av1, "video_latent"); g.link(sa, av1, "audio_latent")
cg1 = g.node("CFGGuider", "cfg 1", (XS + 340, 440), {"cfg": 1.0}, kind="gen")
g.link(ic, cg1, "model"); g.link(sp, cg1, "positive"); g.link(sn, cg1, "negative")
nz = g.node("RandomNoise", "noise", (XS + 340, 560), {}, kind="gen")
g.link(seed, nz, "noise_seed")
k1 = g.node("KSamplerSelect", "euler_ancestral", (XS + 340, 680), {"sampler_name": "euler_ancestral"}, kind="gen")
s1s = g.node("ManualSigmas", "distilled 8-step", (XS + 340, 780), {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}, kind="gen")
s1 = g.node("SamplerCustomAdvanced", "Stage 1 · 절반 해상도", (XS + 340, 900), {}, kind="gen")
g.link(nz, s1, "noise"); g.link(cg1, s1, "guider"); g.link(k1, s1, "sampler"); g.link(s1s, s1, "sigmas"); g.link(av1, s1, "latent_image")
sep1 = g.node("LTXVSeparateAVLatent", "분리", (XS + 340, 1060), {}, kind="gen")
g.link(s1[1], sep1, "av_latent")
crop = g.node("LTXVCropGuides", "가이드 토큰 제거", (XS + 340, 1170), {}, kind="gen")
g.link(sp, crop, "positive"); g.link(sn, crop, "negative"); g.link(sep1[0], crop, "latent")
d1 = g.node("VAEDecodeTiled", "stage1 디코드", (XS + 680, 0), {"tile_size": 512, "overlap": 64, "temporal_size": 128, "temporal_overlap": 32}, kind="gen")
g.link(crop[2], d1, "samples"); g.link(vae, d1, "vae")
b1 = g.node("LTXVLaplacianPyramidBlend", "stage1 원본 영역 복원 (공식 dilation 5)", (XS + 680, 160),
            {"trim_to_shortest": True, "mask_low_res_dilation": 5}, kind="color")
g.link(d1, b1, "image_a"); g.link(green1, b1, "image_b"); g.link(m1, b1, "mask")
g.group("Stage 1 — 절반 해상도 8 step (공식)", (XS - 30, -60, 1040, 1360), "#9A1F50")

# ─────────────── Stage 2 ───────────────
X2 = XS + 1080
u2 = g.node("ImageScale", "stage2 해상도로 확대", (X2, 0), {"upscale_method": "lanczos", "crop": "disabled"}, kind="gen")
g.link(b1, u2, "image"); g.link(Wg["INT"], u2, "width"); g.link(Hg["INT"], u2, "height")
enc2 = g.node("VAEEncodeTiled", "stage2 인코드", (X2, 180), {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}, kind="gen")
g.link(u2, enc2, "pixels"); g.link(vae, enc2, "vae")
aref2 = g.node("LTXVSetAudioRefTokens", "오디오 고정", (X2, 360), {}, kind="gen")
g.link(crop[0], aref2, "positive"); g.link(crop[1], aref2, "negative"); g.link(sep1[1], aref2, "audio_latent")
av2 = g.node("LTXVConcatAVLatent", "AV latent", (X2, 500), {}, kind="gen")
g.link(enc2, av2, "video_latent"); g.link(aref2[2], av2, "audio_latent")
msk2 = g.node("LTXVSetAudioVideoMaskByTime", "원본 영역 latent 고정 · 바깥만 정제 (공간 마스크)", (X2 + 340, 0),
              {"start_time": 0.0, "end_time": 2000.0, "mask_video": True, "mask_audio": False,
               "mask_init_value_video": 0.0, "mask_init_value_audio": 0.0, "slope_len": 3}, kind="guide")
g.link(av2, msk2, "av_latent"); g.link(aref2[0], msk2, "positive"); g.link(aref2[1], msk2, "negative")
g.link(ic, msk2, "model"); g.link(vae, msk2, "vae"); g.link(avae, msk2, "audio_vae"); g.link(fps, msk2, "video_fps")
g.link(spm, msk2, "spatial_mask")
cg2 = g.node("CFGGuider", "cfg 1", (X2, 610), {"cfg": 1.0}, kind="gen")
g.link(ic, cg2, "model"); g.link(msk2[0], cg2, "positive"); g.link(msk2[1], cg2, "negative")
k2 = g.node("KSamplerSelect", "euler", (X2, 730), {"sampler_name": "euler"}, kind="gen")
s2s = g.node("ManualSigmas", "공식 refine", (X2, 830), {"sigmas": "0.7250, 0.4219, 0.0"}, kind="gen")
s2 = g.node("SamplerCustomAdvanced", "Stage 2 · 고해상도 정제", (X2, 950), {}, kind="gen")
g.link(nz, s2, "noise"); g.link(cg2, s2, "guider"); g.link(k2, s2, "sampler"); g.link(s2s, s2, "sigmas"); g.link(msk2[2], s2, "latent_image")
sep2 = g.node("LTXVSeparateAVLatent", "분리", (X2, 1110), {}, kind="gen")
g.link(s2[0], sep2, "av_latent")
d2 = g.node("VAEDecodeTiled", "stage2 디코드", (X2, 1220), {"tile_size": 512, "overlap": 64, "temporal_size": 128, "temporal_overlap": 32}, kind="gen")
g.link(sep2[0], d2, "samples"); g.link(vae, d2, "vae")
g.group("Stage 2 — 원본 영역 고정 + 바깥만 고해상도 정제", (X2 - 30, -60, 740, 1420), "#9A1F50")

# ─────────────── 원본 1:1 복원 · 색 보정 ───────────────
XF = X2 + 780
dc = g.node("ImageScale", "최종 캔버스 크기로", (XF, 0), {"upscale_method": "lanczos", "crop": "disabled"}, kind="post")
g.link(d2, dc, "image"); g.link(Wc["INT"], dc, "width"); g.link(Hc["INT"], dc, "height")
comp0 = g.node("ImageCompositeMasked", "원본 1:1 붙이기 (색 기준용)", (XF, 180), {"resize_source": False}, kind="post")
g.link(dc, comp0, "destination"); g.link(fM, comp0, "source"); g.link(PX["INT"], comp0, "x"); g.link(PY["INT"], comp0, "y")
cmn = g.node("ColorMatchV2", "생성 결과 전체 색을 원본에 맞춤 (프레임별)", (XF, 380), {"method": "mkl"}, kind="color")
g.link(dc, cmn, "image_target"); g.link(comp0, cmn, "image_ref"); g.link(cm_s, cmn, "strength")
comp = g.node("ImageCompositeMasked", "원본 1:1 붙이기", (XF, 580), {"resize_source": False}, kind="post")
g.link(cmn, comp, "destination"); g.link(fM, comp, "source"); g.link(PX["INT"], comp, "x"); g.link(PY["INT"], comp, "y")
fb = g.node("LTXVLaplacianPyramidBlend", "Laplacian 경계 블렌드 (원본 디테일 유지 · 저주파만 연결)", (XF, 780),
            {"trim_to_shortest": True}, kind="color")
g.link(cmn, fb, "image_a"); g.link(comp, fb, "image_b"); g.link(pad[1], fb, "mask"); g.link(dil, fb, "mask_low_res_dilation")
trim = g.node("ImageFromBatch", "원래 프레임 수로 복원", (XF, 980), {}, kind="post")
g.link(fb, trim, "image"); g.link(N, trim, "length")
asw = g.node("ComfySwitchNode", "⑥ 원본 오디오 그대로", (XF, 1120), {}, kind="param")
g.link(vid[2], asw, "on_true"); g.link(has_audio, asw, "switch")
g.group("원본 1:1 복원 — 딱딱한 합성 대신 Laplacian 블렌드", (XF - 30, -60, 400, 1300), "#006F89")

XO = XF + 440
out = g.node("VHS_VideoCombine", "⑩ 최종 MP4", (XO, 0),
             {"filename_prefix": "LTX2.5_Outpaint/outpaint", "format": "video/h264-mp4", "crf": 10}, kind="out", size=[460, 560])
g.link(trim, out, "images"); g.link(asw, out, "audio"); g.link(fps, out, "frame_rate")
g.group("출력", (2070, -60, 520, 660), "#287A32", main=True)

g.note("사용법 · 원리", """# LTX-2.5 아웃페인트 (원본 1:1 보존)

## 무엇이 달라졌나 (Lightricks 공식 2.5 Outpaint 2-stage 기준)
- **distilled 트랜스포머 + In/Outpaint IC-LoRA** (dev + distilled LoRA 조합 제거). 공식 2.5 예제도 2.3 In/Outpaint LoRA를 그대로 씀 — 2.5 전용판은 아직 없음
- **2-stage**: 절반 해상도 8 step → 원본 영역 Laplacian 복원 → 확대·재인코드 → 3-sigma 정제.
- **Stage 2에서 원본 영역을 latent로 고정** (공식 Retake 노드의 spatial_mask). 바깥 영역이 "다시 그려진 가운데"가 아니라 실제 원본에 맞춰 정제되므로, 원본과 생성 영역이 따로 노는 현상이 줄어듦 RTX 업스케일 제거 (표준 ComfyUI에 없는 노드이기도 함)
- 최종 합성: 기존 `ImageCompositeMasked`(딱딱한 붙이기)는 경계에 색 단차가 생김 → **Laplacian 피라미드 블렌드**로 교체. 원본 영역의 세부 픽셀은 그대로, 경계의 저주파(색·밝기)만 부드럽게 이어짐
- ⑧ 생성 영역 전체를 원본 색에 맞춤 (재생성된 중앙 ↔ 원본 중앙 차이로 보정) → 색 털림 방지
- **원본 fps 유지**, 원본 오디오를 모델에 고정 입력 + 출력은 원본 오디오 그대로
- 프레임 수가 8n+1이 아니면 마지막 프레임 반복으로 채운 뒤 원래 길이로 잘라냄

## 팁
- 캔버스: 16:9 원본 → 21:9 선택 시 1920×1080 → 2560×1088 (원본은 가운데 1:1)
- ④ 생성 상한 1920이면 2560 캔버스는 1920×832에서 생성 후 확대. VRAM 여유 있으면 2560
- 경계에 선이 보이면 ⑨를 2~4 (원본 가장자리 일부가 재생성 영역과 섞임)
- ③ 바깥 배경을 구체적으로 쓰면 복제·반복 물체가 줄어듦
""", (0, 1080), size=[900, 600])

note_key = g.nodes[-1]["key"]  # 사용법 노트
g.core("LTX-2.5 OUTPAINT CORE", "LTX-2.5 아웃페인트 CORE  (더블클릭=내부 진입)", (1440, 0),
       [n["key"] for n in g.nodes[:MAIN_UPTO]] + [out, note_key],
       relocate={out: (2100, 0)}, color="gen",
       out_labels={"원본 fps": "fps", "⑦ 소리 없으면 무음 출력": "최종 오디오", "⑥ 원본 오디오 그대로": "최종 오디오", "⑧ 오디오": "최종 오디오", "원본 + 연장 (이음새 크로스페이드)": "최종 영상 (원본+연장)"})

build(g, sys.argv[1] if len(sys.argv) > 1 else "/opt/cf/out_outpaint.json")
