"""LTX-2.5 Union Control (MoGe depth) — official two-stage distilled structure."""
import sys
from builder import G, build

g = G()

def math(expr, title, pos, *srcs):
    n = g.node("ComfyMathExpression", title, pos, {"expression": expr}, kind="param", size=[300, 110])
    for i, s in enumerate(srcs):
        g.link(s, n, "values." + "abcde"[i])
    return n

# ─────────────── 조작 패널 ───────────────
cv = g.node("LoadVideo", "① 제어용 원본 영상 (움직임·구도)", (0, 0), {"file": "test.mp4"}, kind="input", size=[420, 420])
img = g.node("LoadImage", "② 첫 프레임 이미지 (외형·스타일)", (0, 460), {"image": "test.png"}, kind="input", size=[420, 420])
use_img = g.node("PrimitiveBoolean", "③ 첫 프레임 이미지 사용", (460, 0), {"value": True}, kind="param")
st = g.node("PrimitiveFloat", "④ 제어 영상 시작 (초)", (460, 110), {"value": 0.0}, kind="param")
du = g.node("PrimitiveFloat", "⑤ 길이 (초)", (460, 220), {"value": 5.0}, kind="param")
short = g.node("PrimitiveInt", "⑥ stage1 짧은 변 (544 공식 · 최종은 2배)", (460, 330), {"value": 544}, kind="param")
seed = g.node("PrimitiveInt", "⑦ seed", (460, 440), {"value": 42}, kind="param")
lora_s = g.node("PrimitiveFloat", "⑧ Union IC-LoRA 강도 (제어 약하면 ↑, 원본 형태 과하면 ↓)", (460, 550), {"value": 1.0}, kind="param")
enh = g.node("PrimitiveBoolean", "⑨ 프롬프트 자동 보강 (첫 프레임 참고)", (460, 660), {"value": False}, kind="param")
prompt = g.node("PrimitiveStringMultiline", "⑩ 프롬프트", (0, 920),
                {"value": "A slow forward dolly shot on a bright, sunlit day in a lush jungle ruin. A lone figure in nature-themed armor stands before a weathered stone arch overgrown with ivy. A textured marble sphere wrapped in twisting vines levitates in the arch's center, spinning slowly. As the camera glides forward, vines sway softly, leaves flutter in the light breeze. Strong golden sunlight streams through the canopy, illuminating the mossy ruins with bright, clear light."},
                kind="input", size=[420, 220])
neg = g.node("PrimitiveStringMultiline", "negative", (460, 780),
             {"value": "pc game, console game, video game, cartoon, childish, ugly, blurry, deformed face, distorted proportions, flicker, color shift, oversaturated"},
             kind="input", size=[420, 150])
g.group("조작 패널 — 여기만 만지면 됩니다", (-30, -60, 950, 1240), "#48538E", main=True)

# ─────────────── 모델 ───────────────
XM = 1000
unet = g.node("UNETLoader", "LTX-2.5 distilled (int8)", (XM, 0),
              {"unet_name": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"}, kind="model")
ic = g.node("LTXICLoRALoaderModelOnly", "Union Control IC-LoRA ref0.5 (공식 2.5 그래프도 2.3 파일 사용)", (XM, 140),
            {"lora_name": "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors"}, kind="model")
g.link(unet, ic, "model"); g.link(lora_s, ic, "strength_model")
clip = g.node("CLIPLoader", "Gemma 4 12B + LTX-2.5 projection", (XM, 300),
              {"clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "type": "ltxv"}, kind="model")
clip_e = g.node("CLIPLoader", "프롬프트 보강용 Gemma 4 e2b", (XM, 440), {"clip_name": "gemma4_e2b_it_bf16.safetensors", "type": "ltxv"}, kind="model")
vae = g.node("VAELoader", "LTX-2.5 Video VAE", (XM, 580), {"vae_name": "ltx-2.5-video-vae-bf16.safetensors"}, kind="model")
avae = g.node("VAELoader", "LTX-2.5 Audio VAE", (XM, 680), {"vae_name": "ltx-2.5-audio-vae-bf16.safetensors"}, kind="model")
upm = g.node("LatentUpscaleModelLoader", "LTX-2.5 공간 업스케일러 x2", (XM, 780),
             {"model_name": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"}, kind="model")
moge = g.node("LoadMoGeModel", "MoGe-2 깊이 모델", (XM, 900), {"model_name": "moge_2_vitl_normal_fp16.safetensors"}, kind="model")
g.group("모델", (XM - 30, -60, 400, 1080), "#5E258B", main=True)

MAIN_UPTO = len(g.nodes)
# ─────────────── 제어 영상 · 깊이 ───────────────
XD = XM + 440
sl = g.node("Video Slice", "구간 자르기", (XD, 0), {"strict_duration": False}, kind="post")
g.link(cv, sl, "video"); g.link(st, sl, "start_time"); g.link(du, sl, "duration")
comp = g.node("GetVideoComponents", "프레임·fps", (XD, 180), {}, kind="post")
g.link(sl, comp, "video")
fps = comp[2]
sz = g.node("GetImageSize", "제어 영상 크기", (XD, 320), {}, kind="post")
g.link(comp[0], sz, "image")
big = math("max(a,b) > 2048", "2048 초과?", (XD, 460), sz[0], sz[1])
rs = g.node("ResizeImagesByLongerEdge", "긴 변 2048로", (XD, 600), {"longer_edge": 2048}, kind="post")
g.link(comp[0], rs, "images")
sw = g.node("ComfySwitchNode", "MoGe 입력 해상도", (XD, 720), {}, kind="param")
g.link(comp[0], sw, "on_false"); g.link(rs, sw, "on_true"); g.link(big["BOOL"], sw, "switch")
mi = g.node("MoGeInference", "MoGe-2 추론", (XD, 840),
            {"resolution_level": 9, "fov_x_degrees": 0.0, "batch_size": 4, "force_projection": True, "apply_mask": True}, kind="post")
g.link(moge, mi, "moge_model"); g.link(sw, mi, "image")
dep = g.node("MoGeRender", "depth (제어 신호)", (XD, 1060), {"output": "depth"}, kind="post")
g.link(mi, dep, "moge_geometry")
depc = g.node("MoGeRender", "depth_colored (확인용)", (XD, 1160), {"output": "depth_colored"}, kind="post")
g.link(mi, depc, "moge_geometry")
g.group("제어 영상 → MoGe-2 깊이", (XD - 30, -60, 400, 1360), "#414B8F")

# ─────────────── 자동 계산 ───────────────
XA = XD + 440
W1 = math("max(64, round(a*c/min(a,b)/32)*32)", "stage1 가로 (32배수)", (XA, 0), sz[0], sz[1], short[0])
H1 = math("max(64, round(b*c/min(a,b)/32)*32)", "stage1 세로 (32배수)", (XA, 140), sz[0], sz[1], short[0])
M = math("floor((a-1)/8)*8+1", "프레임 수 (8n+1)", (XA, 280), sz[2])
g.group("자동 계산", (XA - 30, -60, 380, 480), "#414B8F")

# ─────────────── 준비 ───────────────
XP = XA + 400
dM = g.node("ImageFromBatch", "깊이 8n+1 프레임", (XP, 0), {}, kind="guide")
g.link(dep, dM, "image"); g.link(M["INT"], dM, "length")
d1 = g.node("ImageScale", "깊이 → stage1 해상도", (XP, 140), {"upscale_method": "bilinear", "crop": "disabled"}, kind="guide")
g.link(dM, d1, "image"); g.link(W1["INT"], d1, "width"); g.link(H1["INT"], d1, "height")
i1 = g.node("ImageScale", "첫 프레임 → stage1 (중앙 크롭)", (XP, 320), {"upscale_method": "lanczos", "crop": "center"}, kind="guide")
g.link(img, i1, "image"); g.link(W1["INT"], i1, "width"); g.link(H1["INT"], i1, "height")
S2W = math("a*2", "stage2 가로", (XP, 500), W1["INT"])
S2H = math("a*2", "stage2 세로", (XP, 640), H1["INT"])
i2 = g.node("ImageScale", "첫 프레임 → stage2", (XP, 780), {"upscale_method": "lanczos", "crop": "center"}, kind="guide")
g.link(img, i2, "image"); g.link(S2W["INT"], i2, "width"); g.link(S2H["INT"], i2, "height")
nb = g.node("ComfyNotNode", "③ 끄면 이미지 무시", (XP, 960), {}, kind="param")
g.link(use_img, nb, "value")
enh_t = g.node("TextGenerateLTX2Prompt", "Gemma 프롬프트 보강 (⑨ 켤 때만)", (XP, 1060), {"max_length": 600}, kind="gen", size=[360, 360])
g.link(clip_e, enh_t, "clip"); g.link(prompt, enh_t, "prompt"); g.link(i1, enh_t, "image")
psw = g.node("ComfySwitchNode", "프롬프트 선택", (XP, 1440), {}, kind="param")
g.link(prompt, psw, "on_false"); g.link(enh_t, psw, "on_true"); g.link(enh, psw, "switch")
pv = g.node("PreviewAny", "실제 사용 프롬프트", (XP, 1540), {}, kind="post")
g.link(psw, pv, "source")
g.group("준비", (XP - 30, -60, 420, 1760), "#6B4500")

# ─────────────── Stage 1 ───────────────
XS = XP + 460
pe = g.node("CLIPTextEncode", "positive", (XS, 0), {}, kind="gen")
g.link(clip, pe, "clip"); g.link(psw, pe, "text")
ne = g.node("CLIPTextEncode", "negative", (XS, 120), {}, kind="gen")
g.link(clip, ne, "clip"); g.link(neg, ne, "text")
cond = g.node("LTXVConditioning", "제어 영상 fps", (XS, 240), {}, kind="gen")
g.link(pe, cond, "positive"); g.link(ne, cond, "negative"); g.link(fps, cond, "frame_rate")
e1 = g.node("EmptyLTXVLatentVideo", "stage1 latent", (XS, 380), {}, kind="gen")
g.link(W1["INT"], e1, "width"); g.link(H1["INT"], e1, "height"); g.link(M["INT"], e1, "length")
ip1 = g.node("LTXVImgToVideoInplace", "첫 프레임 고정", (XS, 540), {"strength": 1.0}, kind="guide")
g.link(vae, ip1, "vae"); g.link(i1, ip1, "image"); g.link(e1, ip1, "latent"); g.link(nb, ip1, "bypass")
gd = g.node("LTXAddVideoICLoRAGuide", "깊이 → Union IC-LoRA 가이드 (ref0.5)", (XS, 720),
            {"frame_idx": 0, "strength": 1.0, "crop": "disabled", "use_tiled_encode": False}, kind="guide")
g.link(cond[0], gd, "positive"); g.link(cond[1], gd, "negative"); g.link(vae, gd, "vae"); g.link(ip1, gd, "latent")
g.link(d1, gd, "image"); g.link(ic[1], gd, "latent_downscale_factor")
ea = g.node("LTXVEmptyLatentAudio", "오디오 latent", (XS, 1040), {}, kind="gen")
g.link(avae, ea, "audio_vae"); g.link(M["INT"], ea, "frames_number"); g.link(fps, ea, "frame_rate")
av1 = g.node("LTXVConcatAVLatent", "AV latent", (XS, 1180), {}, kind="gen")
g.link(gd[2], av1, "video_latent"); g.link(ea, av1, "audio_latent")
cg1 = g.node("CFGGuider", "cfg 1", (XS + 340, 0), {"cfg": 1.0}, kind="gen")
g.link(ic, cg1, "model"); g.link(gd[0], cg1, "positive"); g.link(gd[1], cg1, "negative")
nz = g.node("RandomNoise", "noise", (XS + 340, 120), {}, kind="gen")
g.link(seed, nz, "noise_seed")
k1 = g.node("KSamplerSelect", "euler_ancestral", (XS + 340, 240), {"sampler_name": "euler_ancestral"}, kind="gen")
s1s = g.node("ManualSigmas", "공식 distilled 8-step (linear_quadratic 대체)", (XS + 340, 340),
             {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}, kind="gen")
s1 = g.node("SamplerCustomAdvanced", "Stage 1", (XS + 340, 460), {}, kind="gen")
g.link(nz, s1, "noise"); g.link(cg1, s1, "guider"); g.link(k1, s1, "sampler"); g.link(s1s, s1, "sigmas"); g.link(av1, s1, "latent_image")
sep1 = g.node("LTXVSeparateAVLatent", "분리", (XS + 340, 620), {}, kind="gen")
g.link(s1[0], sep1, "av_latent")
crop = g.node("LTXVCropGuides", "가이드 토큰 제거", (XS + 340, 730), {}, kind="gen")
g.link(gd[0], crop, "positive"); g.link(gd[1], crop, "negative"); g.link(sep1[0], crop, "latent")
g.group("Stage 1 — 공식 Union (8 step)", (XS - 30, -60, 720, 1380), "#9A1F50")

# ─────────────── Stage 2 ───────────────
X2 = XS + 760
up = g.node("LTXVLatentUpsampler", "latent 2배", (X2, 0), {}, kind="gen")
g.link(crop[2], up, "samples"); g.link(upm, up, "upscale_model"); g.link(vae, up, "vae")
ip2 = g.node("LTXVImgToVideoInplace", "첫 프레임 풀해상도 고정", (X2, 140), {"strength": 1.0}, kind="guide")
g.link(vae, ip2, "vae"); g.link(i2, ip2, "image"); g.link(up, ip2, "latent"); g.link(nb, ip2, "bypass")
av2 = g.node("LTXVConcatAVLatent", "AV latent", (X2, 320), {}, kind="gen")
g.link(ip2, av2, "video_latent"); g.link(sep1[1], av2, "audio_latent")
cg2 = g.node("CFGGuider", "cfg 1", (X2, 430), {"cfg": 1.0}, kind="gen")
g.link(ic, cg2, "model"); g.link(crop[0], cg2, "positive"); g.link(crop[1], cg2, "negative")
k2 = g.node("KSamplerSelect", "euler_ancestral", (X2, 550), {"sampler_name": "euler_ancestral"}, kind="gen")
s2s = g.node("ManualSigmas", "공식 refine", (X2, 650), {"sigmas": "0.909375, 0.725, 0.421875, 0.0"}, kind="gen")
s2 = g.node("SamplerCustomAdvanced", "Stage 2 · 2배 해상도", (X2, 770), {}, kind="gen")
g.link(nz, s2, "noise"); g.link(cg2, s2, "guider"); g.link(k2, s2, "sampler"); g.link(s2s, s2, "sigmas"); g.link(av2, s2, "latent_image")
sep2 = g.node("LTXVSeparateAVLatent", "분리", (X2, 930), {}, kind="gen")
g.link(s2[0], sep2, "av_latent")
dec = g.node("VAEDecodeTiled", "디코드", (X2, 1040), {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}, kind="gen")
g.link(sep2[0], dec, "samples"); g.link(vae, dec, "vae")
adec = g.node("LTXVAudioVAEDecode", "오디오 디코드", (X2, 1220), {}, kind="gen")
g.link(sep2[1], adec, "samples"); g.link(avae, adec, "audio_vae")
g.group("Stage 2 — 공식 upscale + re-sample (3 step)", (X2 - 30, -60, 400, 1420), "#9A1F50")

XO = X2 + 440
out = g.node("VHS_VideoCombine", "⑪ 결과", (XO, 0),
             {"filename_prefix": "LTX2.5_Union/union_depth", "format": "video/h264-mp4", "crf": 12}, kind="out", size=[460, 560])
g.link(dec, out, "images"); g.link(adec, out, "audio"); g.link(fps, out, "frame_rate")
pv1 = g.node("PreviewImage", "깊이 확인 (엔진 입력)", (XO, 620), {}, kind="out", size=[420, 300])
g.link(d1, pv1, "images")
pv2 = g.node("PreviewImage", "깊이 품질 확인 · depth_colored", (XO, 960), {}, kind="out", size=[420, 300])
g.link(depc, pv2, "images")
g.group("출력 · 확인", (2070, -60, 520, 1380), "#287A32", main=True)

g.note("사용법 · 원리", """# LTX-2.5 Union Control (MoGe-2 depth)

## 무엇이 달라졌나 (Lightricks 공식 2.5 Union 그래프 기준)
- 샘플러: `KSampler + linear_quadratic 8 step` → **공식 distilled sigma 8개** (`ManualSigmas`). distilled 모델은 이 sigma로 학습됨
- **2-stage**: 제어 영상 비율 그대로 짧은 변 544 → latent x2 → 3 step 재샘플 (최종 짧은 변 1088)
- 고정 1280×704 대신 **제어 영상 비율 자동** (32배수) · fps도 제어 영상에서 자동
- Union IC-LoRA는 공식 `LTXICLoRALoaderModelOnly` + `LTXAddVideoICLoRAGuide` 경로 (ref0.5 다운스케일 자동)
- 첫 프레임은 stage 2에서도 다시 고정 → 인물 얼굴·외형 유지

## 팁
- 깊이 미리보기부터 확인: 엔진(Stage 1/2)을 Ctrl+B로 끄고 실행하면 깊이만 빠르게 나옴
- Union IC-LoRA 2.5 전용판은 아직 없음 → 공식 2.5 예제도 2.3 ref0.5 파일을 그대로 사용
""", (0, 1180), size=[900, 520])

note_key = g.nodes[-1]["key"]  # 사용법 노트
g.core("LTX-2.5 UNION CONTROL CORE", "LTX-2.5 Union Control CORE  (더블클릭=내부 진입)", (1440, 0),
       [n["key"] for n in g.nodes[:MAIN_UPTO]] + [out, pv1, pv2, note_key],
       relocate={out: (2100, 0), pv1: (2100, 620), pv2: (2100, 960)}, color="gen")

build(g, sys.argv[1] if len(sys.argv) > 1 else "/opt/cf/out_union.json")
