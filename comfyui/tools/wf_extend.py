"""LTX-2.5 video extension (retake-style latent continuation) workflow."""
import sys
from builder import G, build

g = G()

def math(expr, title, pos, *srcs, kind="param"):
    n = g.node("ComfyMathExpression", title, pos, {"expression": expr}, kind=kind, size=[300, 110])
    for i, s in enumerate(srcs):
        g.link(s, n, "values." + "abcde"[i])
    return n

# ─────────────────────────── 조작 패널 ───────────────────────────
X0 = 0
vid = g.node("VHS_LoadVideo", "① 원본 영상 (fps 변경 없음)", (X0, 0),
             {"video": "test.mp4", "force_rate": 0, "frame_load_cap": 0, "format": "None"}, kind="input", size=[420, 600])
prompt = g.node("PrimitiveStringMultiline", "② 이어질 장면 설명 (인물 외형·의상·조명을 구체적으로)", (X0, 660),
                {"value": "The same person continues the motion naturally, same face, same hairstyle, same clothing, same lighting and color grade, same camera framing and lens. Smooth, continuous movement without cuts."},
                kind="input", size=[420, 200])
neg = g.node("PrimitiveStringMultiline", "negative", (X0, 880),
             {"value": "deformed face, distorted face, melting face, blurry face, changing identity, different person, extra fingers, color shift, oversaturated, washed out, flicker, sudden cut, scene change, fade to black, freeze frame, text, watermark, subtitles"},
             kind="input", size=[420, 150])
sec = g.node("PrimitiveFloat", "③ 추가할 길이 (초)", (X0 + 460, 0), {"value": 3.0}, kind="param")
ctxn = g.node("PrimitiveInt", "④ 고정할 원본 문맥 프레임 (8n+1 · 49 권장, 얼굴 불안하면 73/97)", (X0 + 460, 110), {"value": 49}, kind="param")
maxl = g.node("PrimitiveInt", "⑤ 생성 해상도 긴 변 상한 (원본보다 크면 원본 기준)", (X0 + 460, 220), {"value": 1920}, kind="param")
seed = g.node("PrimitiveInt", "⑥ seed", (X0 + 460, 330), {"value": 42}, kind="param")
has_audio = g.node("PrimitiveBoolean", "⑦ 원본에 소리가 있음 (무음 영상이면 끄기)", (X0 + 460, 440), {"value": True}, kind="param")
cm_str = g.node("PrimitiveFloat", "⑧ 색 일치 강도 (0=끔 · 0.5 권장 · 1=완전 일치)", (X0 + 460, 550), {"value": 0.5}, kind="param")
seam = g.node("PrimitiveInt", "⑨ 이음새 크로스페이드 프레임", (X0 + 460, 660), {"value": 4}, kind="param")
enh = g.node("PrimitiveBoolean", "⑩ 프롬프트 자동 보강 (Gemma, 원본 마지막 프레임 참고)", (X0 + 460, 770), {"value": False}, kind="param")
g.group("조작 패널 — 여기만 만지면 됩니다", (X0 - 30, -60, 950, 1120), "#48538E")

# ─────────────────────────── 모델 ───────────────────────────
XM = X0 + 1000
unet = g.node("UNETLoader", "LTX-2.5 distilled (int8)", (XM, 0),
              {"unet_name": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"}, kind="model")
clip = g.node("CLIPLoader", "Gemma 4 12B + LTX-2.5 projection", (XM, 140),
              {"clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "type": "ltxv"}, kind="model")
clip_e = g.node("CLIPLoader", "프롬프트 보강용 Gemma 4 e2b", (XM, 280),
                {"clip_name": "gemma4_e2b_it_bf16.safetensors", "type": "ltxv"}, kind="model")
vae = g.node("VAELoader", "LTX-2.5 Video VAE (고화질 디퓨전 디코더)", (XM, 420),
             {"vae_name": "ltx-2.5-video-vae-bf16.safetensors"}, kind="model")
avae = g.node("VAELoader", "LTX-2.5 Audio VAE", (XM, 520), {"vae_name": "ltx-2.5-audio-vae-bf16.safetensors"}, kind="model")
upm = g.node("LatentUpscaleModelLoader", "LTX-2.5 공간 업스케일러 x2", (XM, 620),
             {"model_name": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"}, kind="model")
g.group("모델 (LTX-2.5 공식 Comfy 파일명)", (XM - 30, -60, 380, 800), "#5E258B")

# ─────────────────────────── 자동 계산 ───────────────────────────
XA = XM + 420
info = g.node("VHS_VideoInfo", "원본 fps", (XA, 0), {}, kind="post")
g.link(vid[3], info, "video_info")
size = g.node("GetImageSize", "원본 가로·세로·프레임 수", (XA, 260), {}, kind="post")
g.link(vid[0], size, "image")
fps = info[5]  # loaded_fps
W0, H0, N = size[0], size[1], size[2]
C = math("min(floor((a-1)/8)*8+1, floor((b-1)/8)*8+1)", "문맥 프레임 C (8n+1 · 원본 길이 이내)", (XA, 400), ctxn[0], N)
NEW = math("max(8, ceil(a*b/8)*8)", "새 프레임 수 (8의 배수)", (XA, 540), sec[0], fps)
TOT = math("a+b", "생성 길이 = C + 새 프레임", (XA, 680), C["INT"], NEW["INT"])
CST = math("a-b", "문맥 시작 인덱스", (XA, 820), N, C["INT"])
Wf = math("max(64, round(a*min(1, c/max(a,b))/64)*64)", "stage2 가로 (64배수)", (XA + 340, 0), W0, H0, maxl[0])
Hf = math("max(64, round(b*min(1, c/max(a,b))/64)*64)", "stage2 세로 (64배수)", (XA + 340, 140), W0, H0, maxl[0])
Wh = math("a//2", "stage1 가로 (절반)", (XA + 340, 280), Wf["INT"])
Hh = math("a//2", "stage1 세로 (절반)", (XA + 340, 420), Hf["INT"])
t_ctx0 = math("a/b", "문맥 시작 시각 (초)", (XA + 340, 560), CST["INT"], fps)
t_ctx = math("a/b", "문맥 길이 (초) = 생성 시작 시각", (XA + 340, 700), C["INT"], fps)
t_end = math("a/b + 1", "생성 끝 시각 (여유 1초)", (XA + 340, 840), TOT["INT"], fps)
t_new = math("a/b", "새 구간 길이 (초)", (XA + 340, 980), NEW["INT"], fps)
TS = math("a-b", "디코드 결과에서 잘라낼 시작 (C - 크로스페이드)", (XA + 340, 1120), C["INT"], seam[0])
TL = math("a+b", "잘라낼 길이 (새 프레임 + 크로스페이드)", (XA + 340, 1260), NEW["INT"], seam[0])
LAST = math("a-1", "원본 마지막 프레임 번호", (XA, 960), N)
g.group("자동 계산 — 손대지 않아도 됩니다", (XA - 30, -60, 720, 1460), "#414B8F")

# ─────────────────────────── 문맥 준비 ───────────────────────────
XC = XA + 760
ctx = g.node("ImageFromBatch", "원본 마지막 C프레임 (고정 문맥)", (XC, 0), {}, kind="guide")
g.link(vid[0], ctx, "image"); g.link(CST["INT"], ctx, "batch_index"); g.link(C["INT"], ctx, "length")
ctx_f = g.node("ImageScale", "문맥 · stage2 해상도", (XC, 160), {"upscale_method": "lanczos", "crop": "disabled"}, kind="guide")
g.link(ctx, ctx_f, "image"); g.link(Wf["INT"], ctx_f, "width"); g.link(Hf["INT"], ctx_f, "height")
ctx_h = g.node("ImageScale", "문맥 · stage1 해상도", (XC, 340), {"upscale_method": "area", "crop": "disabled"}, kind="guide")
g.link(ctx, ctx_h, "image"); g.link(Wh["INT"], ctx_h, "width"); g.link(Hh["INT"], ctx_h, "height")
last = g.node("ImageFromBatch", "원본 마지막 1프레임 (색 기준 · 프롬프트 보강 참고)", (XC, 520), {}, kind="guide")
g.link(vid[0], last, "image"); g.link(LAST["INT"], last, "batch_index")
a_ctx = g.node("TrimAudioDuration", "문맥 구간 원본 오디오", (XC, 680), {}, kind="guide")
g.link(vid[2], a_ctx, "audio"); g.link(t_ctx0["FLOAT"], a_ctx, "start_index"); g.link(t_ctx["FLOAT"], a_ctx, "duration")
a_enc = g.node("LTXVAudioVAEEncode", "문맥 오디오 인코드 (소리 이어짐)", (XC, 840), {}, kind="guide")
g.link(a_ctx, a_enc, "audio"); g.link(avae, a_enc, "audio_vae")

# 프롬프트
enh_t = g.node("TextGenerateLTX2Prompt", "Gemma 프롬프트 보강 (⑩ 켤 때만 실행)", (XC, 980),
               {"max_length": 600}, kind="gen", size=[360, 380])
g.link(clip_e, enh_t, "clip"); g.link(prompt, enh_t, "prompt"); g.link(last, enh_t, "image")
psw = g.node("ComfySwitchNode", "프롬프트 선택", (XC, 1400), {}, kind="param")
g.link(prompt, psw, "on_false"); g.link(enh_t, psw, "on_true"); g.link(enh, psw, "switch")
pv = g.node("PreviewAny", "실제 사용 프롬프트", (XC, 1520), {}, kind="post")
g.link(psw, pv, "source")
g.group("문맥 준비 — 원본은 절대 재생성하지 않음", (XC - 30, -60, 440, 1760), "#6B4500")

# ─────────────────────────── Stage 1 ───────────────────────────
XS = XC + 480
pos_e = g.node("CLIPTextEncode", "positive", (XS, 0), {}, kind="gen")
g.link(clip, pos_e, "clip"); g.link(psw, pos_e, "text")
neg_e = g.node("CLIPTextEncode", "negative", (XS, 120), {}, kind="gen")
g.link(clip, neg_e, "clip"); g.link(neg, neg_e, "text")
cond = g.node("LTXVConditioning", "원본 fps로 조건", (XS, 240), {}, kind="gen")
g.link(pos_e, cond, "positive"); g.link(neg_e, cond, "negative"); g.link(fps, cond, "frame_rate")
ev = g.node("EmptyLTXVLatentVideo", "stage1 빈 latent (C + 새 프레임)", (XS, 380), {}, kind="gen")
g.link(Wh["INT"], ev, "width"); g.link(Hh["INT"], ev, "height"); g.link(TOT["INT"], ev, "length")
inp1 = g.node("LTXVImgToVideoInplace", "문맥 C프레임 latent 고정 (strength 1)", (XS, 560), {"strength": 1.0}, kind="guide")
g.link(vae, inp1, "vae"); g.link(ctx_h, inp1, "image"); g.link(ev, inp1, "latent")
ea = g.node("LTXVEmptyLatentAudio", "빈 오디오 latent", (XS, 720), {}, kind="gen")
g.link(avae, ea, "audio_vae"); g.link(TOT["INT"], ea, "frames_number"); g.link(fps, ea, "frame_rate")
av0 = g.node("LTXVConcatAVLatent", "AV latent", (XS, 880), {}, kind="gen")
g.link(inp1, av0, "video_latent"); g.link(ea, av0, "audio_latent")
av_ctx = g.node("LTXVConcatAVLatent", "문맥 오디오 삽입 (뒤는 0 패딩 → 생성)", (XS, 980), {}, kind="gen")
g.link(av0, av_ctx, "video_latent"); g.link(a_enc, av_ctx, "audio_latent")
asw = g.node("ComfySwitchNode", "⑦ 소리 있음? 문맥 오디오 사용", (XS, 1080), {}, kind="param")
g.link(av0, asw, "on_false"); g.link(av_ctx, asw, "on_true"); g.link(has_audio, asw, "switch")
msk1 = g.node("LTXVSetAudioVideoMaskByTime", "Retake 마스크 · 문맥=고정 / 이후=생성", (XS + 340, 0),
              {"mask_video": True, "mask_audio": True, "mask_init_value_video": 0.0, "mask_init_value_audio": 0.0, "slope_len": 3},
              kind="guide")
g.link(asw, msk1, "av_latent"); g.link(cond[0], msk1, "positive"); g.link(cond[1], msk1, "negative")
g.link(unet, msk1, "model"); g.link(vae, msk1, "vae"); g.link(avae, msk1, "audio_vae")
g.link(t_ctx["FLOAT"], msk1, "start_time"); g.link(t_end["FLOAT"], msk1, "end_time"); g.link(fps, msk1, "video_fps")
gd1 = g.node("CFGGuider", "distilled · cfg 1", (XS + 340, 420), {"cfg": 1.0}, kind="gen")
g.link(unet, gd1, "model"); g.link(msk1[0], gd1, "positive"); g.link(msk1[1], gd1, "negative")
nz1 = g.node("RandomNoise", "noise", (XS + 340, 540), {}, kind="gen")
g.link(seed, nz1, "noise_seed")
sm1 = g.node("KSamplerSelect", "euler_ancestral (공식 stage1)", (XS + 340, 660), {"sampler_name": "euler_ancestral"}, kind="gen")
sg1 = g.node("ManualSigmas", "공식 distilled 8-step", (XS + 340, 760),
             {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}, kind="gen")
s1 = g.node("SamplerCustomAdvanced", "Stage 1 · 절반 해상도 생성", (XS + 340, 880), {}, kind="gen")
g.link(nz1, s1, "noise"); g.link(gd1, s1, "guider"); g.link(sm1, s1, "sampler"); g.link(sg1, s1, "sigmas"); g.link(msk1[2], s1, "latent_image")
sep1 = g.node("LTXVSeparateAVLatent", "분리", (XS + 340, 1040), {}, kind="gen")
g.link(s1[0], sep1, "av_latent")
g.group("Stage 1 — 절반 해상도 · 8 step · 문맥 고정 연장", (XS - 30, -60, 720, 1260), "#9A1F50")

# ─────────────────────────── Stage 2 ───────────────────────────
X2 = XS + 760
up = g.node("LTXVLatentUpsampler", "latent 2배 업스케일", (X2, 0), {}, kind="gen")
g.link(sep1[0], up, "samples"); g.link(upm, up, "upscale_model"); g.link(vae, up, "vae")
inp2 = g.node("LTXVImgToVideoInplace", "문맥 풀해상도로 다시 고정", (X2, 140), {"strength": 1.0}, kind="guide")
g.link(vae, inp2, "vae"); g.link(ctx_f, inp2, "image"); g.link(up, inp2, "latent")
av2 = g.node("LTXVConcatAVLatent", "AV latent (stage1 오디오 재사용)", (X2, 300), {}, kind="gen")
g.link(inp2, av2, "video_latent"); g.link(sep1[1], av2, "audio_latent")
msk2 = g.node("LTXVSetAudioVideoMaskByTime", "Stage2 마스크 · 오디오 전체 고정", (X2, 420),
              {"mask_video": True, "mask_audio": False, "mask_init_value_video": 0.0, "mask_init_value_audio": 0.0, "slope_len": 3},
              kind="guide")
g.link(av2, msk2, "av_latent"); g.link(cond[0], msk2, "positive"); g.link(cond[1], msk2, "negative")
g.link(unet, msk2, "model"); g.link(vae, msk2, "vae"); g.link(avae, msk2, "audio_vae")
g.link(t_ctx["FLOAT"], msk2, "start_time"); g.link(t_end["FLOAT"], msk2, "end_time"); g.link(fps, msk2, "video_fps")
gd2 = g.node("CFGGuider", "distilled · cfg 1", (X2, 840), {"cfg": 1.0}, kind="gen")
g.link(unet, gd2, "model"); g.link(msk2[0], gd2, "positive"); g.link(msk2[1], gd2, "negative")
sm2 = g.node("KSamplerSelect", "euler (정제 · 디테일 보존)", (X2, 960), {"sampler_name": "euler"}, kind="gen")
sg2 = g.node("ManualSigmas", "공식 refine 3-step", (X2, 1060), {"sigmas": "0.85, 0.7250, 0.4219, 0.0"}, kind="gen")
s2 = g.node("SamplerCustomAdvanced", "Stage 2 · 풀해상도 정제 (얼굴 디테일)", (X2, 1180), {}, kind="gen")
g.link(nz1, s2, "noise"); g.link(gd2, s2, "guider"); g.link(sm2, s2, "sampler"); g.link(sg2, s2, "sigmas"); g.link(msk2[2], s2, "latent_image")
sep2 = g.node("LTXVSeparateAVLatent", "분리", (X2, 1340), {}, kind="gen")
g.link(s2[0], sep2, "av_latent")
dec = g.node("VAEDecodeTiled", "비디오 디코드", (X2 + 340, 0), {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}, kind="gen")
g.link(sep2[0], dec, "samples"); g.link(vae, dec, "vae")
adec = g.node("LTXVAudioVAEDecode", "오디오 디코드", (X2 + 340, 200), {}, kind="gen")
g.link(sep2[1], adec, "samples"); g.link(avae, adec, "audio_vae")
g.group("Stage 2 — 2배 latent 업스케일 + 3 step 정제 (RTX 재그리기 없음)", (X2 - 30, -60, 720, 1560), "#9A1F50")

# ─────────────────────────── 합치기 · 색 보정 ───────────────────────────
XP = X2 + 760
rs = g.node("ImageScale", "생성 결과 → 원본 해상도 정확히", (XP, 0), {"upscale_method": "lanczos", "crop": "disabled"}, kind="post")
g.link(dec, rs, "image"); g.link(W0, rs, "width"); g.link(H0, rs, "height")
tail = g.node("ImageFromBatch", "새 프레임 (+크로스페이드분)만 추출", (XP, 180), {}, kind="post")
g.link(rs, tail, "image"); g.link(TS["INT"], tail, "batch_index"); g.link(TL["INT"], tail, "length")
cmn = g.node("ColorMatchV2", "원본 마지막 프레임 기준 색 일치 (색 털림 방지)", (XP, 340), {"method": "mkl"}, kind="color")
g.link(tail, cmn, "image_target"); g.link(last, cmn, "image_ref"); g.link(cm_str, cmn, "strength")
ext = g.node("ImageBatchExtendWithOverlap", "원본 + 연장 (이음새 크로스페이드)", (XP, 540),
             {"overlap_side": "source", "overlap_mode": "linear_blend"}, kind="post")
g.link(vid[0], ext, "source_images"); g.link(seam, ext, "overlap"); g.link(cmn, ext, "new_images")
a_new = g.node("TrimAudioDuration", "생성 오디오 · 새 구간만", (XP, 740), {}, kind="post")
g.link(adec, a_new, "audio"); g.link(t_ctx["FLOAT"], a_new, "start_index"); g.link(t_new["FLOAT"], a_new, "duration")
a_cat = g.node("AudioConcat", "원본 오디오 + 새 오디오", (XP, 900), {"direction": "after"}, kind="post")
g.link(vid[2], a_cat, "audio1"); g.link(a_new, a_cat, "audio2")
a_sw = g.node("ComfySwitchNode", "⑦ 소리 없으면 무음 출력", (XP, 1040), {}, kind="param")
g.link(a_cat, a_sw, "on_true"); g.link(has_audio, a_sw, "switch")
g.group("합치기 — 원본 프레임 무변형 + 색 보정 + 이음새 처리", (XP - 30, -60, 400, 1260), "#006F89")

# ─────────────────────────── 출력 ───────────────────────────
XO = XP + 440
out = g.node("VHS_VideoCombine", "⑪ 최종 MP4 (원본 + 연장)", (XO, 0),
             {"filename_prefix": "LTX2.5_Extend/extend", "format": "video/h264-mp4", "crf": 12}, kind="out", size=[460, 560])
g.link(ext[2], out, "images"); g.link(a_sw, out, "audio"); g.link(fps, out, "frame_rate")
out2 = g.node("VHS_VideoCombine", "⑫ ProRes (AE 합성용 · 필요 시 Ctrl+M 해제)", (XO, 620),
              {"filename_prefix": "LTX2.5_Extend/extend_prores", "format": "video/ProRes"}, kind="out", mode=2, size=[460, 400])
g.link(ext[2], out2, "images"); g.link(a_sw, out2, "audio"); g.link(fps, out2, "frame_rate")
g.group("출력", (XO - 30, -60, 520, 1120), "#287A32")

g.note("사용법 · 원리", """# LTX-2.5 길이 연장 (Retake 방식)

**조작 패널 ①~⑩만 만지면 됩니다.**

## 무엇이 달라졌나
- 원본 **마지막 C프레임(기본 49 ≈ 2초)** 을 latent에 넣고 noise mask 0으로 **고정** → 모델이 얼굴·옷·조명을 2초 분량 그대로 보면서 뒤만 생성합니다. (공식 `RetakePipeline`과 같은 원리, 9프레임 가이드보다 얼굴 유지력이 훨씬 높음)
- 원본 **소리도 문맥으로 고정** → 새 구간 소리가 자연스럽게 이어짐 (⑦ 무음 영상이면 끄기)
- **2-stage**: 절반 해상도 8 step → 공식 latent 업스케일러 x2 → 풀해상도 3 step 정제. RTX 업스케일로 얼굴을 다시 그리지 않음
- **원본 fps 유지** (force_rate 0). 기존 24fps 강제 변환 제거
- 원본 프레임은 한 장도 재생성하지 않고 그대로 출력. 이음새는 ⑨ 4프레임 크로스페이드
- ⑧ 새 프레임을 원본 마지막 프레임 색에 맞춤 (mkl). 장면 조명이 크게 바뀌는 연장이면 0.2~0.3

## 얼굴이 흔들릴 때
1. ④ 문맥을 73 또는 97로 (VRAM 여유 있으면)
2. ② 프롬프트에 인물 외형을 구체적으로 (머리·의상·나이·표정)
3. ③ 한 번에 3~5초 이하로 나눠 연장 → 결과를 다시 입력
4. seed만 바꿔 2~3회 뽑고 고르기

## 참고
- 생성 해상도는 64배수로 맞춘 뒤(최대 0.7% 비율 오차) 최종 출력은 원본 가로·세로로 정확히 복원
- 새 프레임 수는 8의 배수로 올림되어 입력한 초보다 약간 길 수 있음
""", (X0, 1100), size=[900, 640])

build(g, sys.argv[1] if len(sys.argv) > 1 else "/opt/cf/out_extend.json")
