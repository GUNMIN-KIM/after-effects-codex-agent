import json
import os

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source")

_basic = json.load(open(os.path.join(_SRC, "WAN_VACE_1.3B_14B_original.json")))
_p = next(n for n in _basic["nodes"] if n["id"] == 6)["widgets_values"][0]
_pos = _p.split("NEGATIVE PROMPT (STRICT):")[0].replace("✅ FINAL PROMPT (Kling / Omni)\n\n", "").strip()

BG_NEGATIVE = ("character change, identity change, duplicated person, extra people, changed pose, changed clothing, "
               "camera movement, zoom, pan, color grading change, relighting, flicker, stylization, CGI look, "
               "blur, noise, banding, halo, edge artifacts, color spill, pitch black void, fantasy, sci-fi objects, "
               "planets, text, watermark, low quality")

_inp = json.load(open(os.path.join(_SRC, "WAN_VACE_Inpaint_original.json")))
_sg = _inp["definitions"]["subgraphs"][0]
_neg_cn = next(n for n in _sg["nodes"] if n["id"] == 279)["widgets_values"][0]

HF = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"
KJ = "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main"


def models_md(sizes):
    rows = []
    if "14B" in sizes:
        rows.append(f"[⬇ wan2.1_vace_14B_fp16.safetensors]({HF}/diffusion_models/wan2.1_vace_14B_fp16.safetensors?download=true)\n\n"
                    "- 저장 위치: `ComfyUI/models/diffusion_models/`\n- 480p · 720p 모두 지원 (`04 RESOLUTION · Canvas 720p` ON 가능)")
    if "1.3B" in sizes:
        rows.append(f"[⬇ wan2.1_vace_1.3B_fp16.safetensors]({HF}/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors?download=true)\n\n"
                    "- 저장 위치: `ComfyUI/models/diffusion_models/`\n- **480p 전용** → `Canvas 720p`를 반드시 OFF")
    body = "\n\n".join(rows)
    loras = [f"[⬇ Wan21_CausVid_14B_T2V_lora_rank32.safetensors]({KJ}/Wan21_CausVid_14B_T2V_lora_rank32.safetensors?download=true) — 14B용"]
    if "1.3B" in sizes:
        loras.append(f"[⬇ Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors]({KJ}/Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors?download=true) — 1.3B용")
    return f"""# 모델 설치 — 파일명을 누르면 바로 다운로드

이 시연본은 **ComfyUI v0.31.1** 기준이며 커스텀 노드 없이 **core 노드만** 사용합니다.

> 링크를 누르면 브라우저 다운로드가 시작됩니다. 다운로드가 끝나면 아래 표시된 ComfyUI 모델 폴더에 넣고 모델 목록을 새로고침하세요.

## 1. Wan VACE Diffusion Model — 필수

{body}

## 2. CausVid 속도 LoRA — Turbo 모드용

{chr(10).join('- ' + l for l in loras)}

- 저장 위치: `ComfyUI/models/loras/`
- **모델 크기와 같은 LoRA**를 고르세요 (14B 모델 + 14B LoRA / 1.3B 모델 + 1.3B LoRA)

## 3. UMT5 Text Encoder — 필수

[⬇ umt5_xxl_fp8_e4m3fn_scaled.safetensors]({HF}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors?download=true)

- 저장 위치: `ComfyUI/models/text_encoders/`

## 4. Wan VAE — 필수

[⬇ wan_2.1_vae.safetensors]({HF}/vae/wan_2.1_vae.safetensors?download=true)

- 저장 위치: `ComfyUI/models/vae/`

## 전체 모델 페이지

[Comfy-Org/Wan_2.1_ComfyUI_repackaged 열기](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/tree/main/split_files) · [Wan-AI/Wan2.1-VACE-14B](https://huggingface.co/Wan-AI/Wan2.1-VACE-14B)

## 주의

- 파일명이 다르게 저장돼 있으면 MAIN CONTROL의 `01 MODEL` · `09 FILES` 항목에서 직접 고르면 됩니다.
- 이전 버전의 `BlockifyMask`(커스텀 노드)는 제거되었고, 같은 기능을 core 노드로 만든 `06 MASK · 8px Block Align`으로 대체했습니다.
- 대용량 파일은 다운로드 완료 전에 ComfyUI 폴더로 옮기거나 이름을 바꾸지 마세요."""


def guide(title, lead, turbo_steps, scale_note):
    return f"""# {title} — 사용 순서

`1. Source Video` → `2. Mask Video` → `3. Reference Image (선택)` → `4. MAIN CONTROL` → `5. Final Output`

{lead}

Source / Mask / Reference를 넣고 **MAIN CONTROL 한 곳에서** Model / LoRA / Prompt / Length·Resolution·FPS Mode / Mask / Strength / Seed를 조절한 뒤 Generate 하면 됩니다. 4k+1 길이 패딩, 마스크 길이 맞춤, 16px Canvas, 원본 프레임 수 복원, Pixel Lock, 오디오 및 FPS 유지는 전부 자동입니다.

## MAIN CONTROL에서 조절하는 항목

- **01 MODEL** · VACE Model · Speed LoRA · LoRA Strength · Turbo (ON = LoRA {turbo_steps} steps CFG 1 / OFF = 20 steps CFG 6)
- **02 PROMPT** · Positive / Negative
- **03 VIDEO** · Length Mode · Duration
- **04 RESOLUTION** · Canvas 720p · Output Scale · Custom Width / Height · Keep Aspect Ratio
- **05 FPS** · FPS Mode · Custom FPS
- **06 MASK** · Invert · Expand(px) · 8px Block Align · Pixel Lock
- **07 VACE** · Control Strength
- **08 SEED** · Seed · Seed Mode
- **09 FILES** · Text Encoder · VAE (파일명이 다를 때만)

## Source / Custom

- **Source (기본값)** — Source Video의 frame count · 해상도 · FPS · 오디오를 그대로 사용합니다.
- **Custom** — 해당 Mode 토글을 켠 항목만 override 됩니다. (`Duration × FPS` = target frames, 소스 길이를 넘지 않음)
- {scale_note}

## Mask Video 규칙

- **흰색 또는 빨강 = 새로 생성할 영역**, 검정 = 원본 유지. 반대로 만든 마스크는 `06 MASK · Invert`를 켜세요.
- 마스크가 소스보다 짧으면 **마지막 마스크 프레임을 유지**합니다. 해상도가 달라도 자동으로 맞춥니다.
- `Pixel Lock` ON이면 마스크 밖은 **원본 픽셀 그대로** 출력됩니다.

`(선택)` 표시 노드(Control Preview, 결과/원본 비교)는 지워도 본 파이프라인에는 영향이 없습니다."""


STRUCTURE = """## 내부 자동 계산 (MAIN CONTROL 안)

- **Target frames** = Source frame count (Custom: `min(source, round(sec × FPS))`)
- **VACE length** = `ceil((target-1)/4)·4+1` → 생성 후 `FINAL TRIM`으로 target 프레임만 남김
- **Canvas** = 원본 비율 유지 · 16px 정렬 · 면적 `832×480`(480p) 또는 `1280×720`(720p)
  - `W = floor(√(area·w/h)/16)·16`, `H = floor(√(area·h/w)/16)·16`
- **Control video** = 원본에서 마스크 영역만 **Gray 0.5**로 채움 (VACE 학습 규칙 `MASK_COLOR = 128`)
- **Mask** = red 채널 → (Invert) → 0.5 Threshold → Expand → (8px Block Align)
- **Output size** = Source × Scale (Custom: 입력값, Keep Aspect면 원본 비율) · **항상 짝수**로 맞춤 (H.264 요구사항)
- **Pixel Lock** = 출력 해상도의 원본 위에 마스크 영역만 VACE 결과를 합성
- **FPS / Audio** = Source FPS와 Source Audio를 최종 CreateVideo에 그대로 전달

## 고정값 (MAIN CONTROL 안에 숨김)

Sampler `uni_pc` · Scheduler `simple` · Model Shift `5` · Normal `20 steps / CFG 6` · Turbo `{turbo} steps / CFG 1` · weight dtype `default`

## 오디오 주의

`05 FPS · Custom`으로 속도를 바꾸면 영상 길이는 바뀌지만 오디오는 원래 속도로 붙습니다."""


def audit(base, extra):
    return {
        "date": "2026-09-24",
        "base_workflow": base,
        "changes": [
            "Creator UI: single MAIN CONTROL subgraph (01 MODEL … 09 FILES) like the Wan Animate 2 panel",
            "Control video fills the masked area with 0.5 gray (VACE MASK_COLOR 128) instead of white",
            "Canvas from source aspect, 16px aligned, 480p or 720p area budget (toggle)",
            "4k+1 VACE length with FINAL TRIM back to the target frame count",
            "Mask video: length matched to source (hold last frame), resized to canvas, red channel, invert, 0.5 threshold, expand, optional 8px block align",
            "Output: Source × Scale or Custom W/H, always even for H.264; optional pixel lock composite at output size",
            "Source FPS and audio carried to the final video; Custom length/FPS modes",
            "Removed custom-node dependency BlockifyMask (was bypassed); core-node block align replaces it",
            "Model links with click-to-download notes and properties.models metadata",
        ] + extra,
        "runtime_verified": "dry-run only: ComfyUI v0.31.1 + frontend 1.48.7 load, graphToPrompt, server validation and execution "
                            "with stubbed model math (loaders/sampler/VAE). Not GPU-rendered; output quality unverified.",
    }


CONFIGS = {
    "basic": dict(
        out="WAN_VACE_1.3B_14B_CreatorUI.json",
        unet="wan2.1_vace_14B_fp16.safetensors",
        lora="Wan21_CausVid_14B_T2V_lora_rank32.safetensors",
        lora_strength=0.5, turbo_steps=4, canvas_720p=True, output_scale=1.0, mask_expand=0,
        seed=336382553413771,
        positive=_pos, negative=BG_NEGATIVE,
        src_file="24ba3974fd872a5c0ec6206e6743b981ba2a7e577e0df4839dda13291796daa5.mp4",
        mask_file="aa50dc77aa170f8a36638065091a3748afe5ebc2049a2b16d491446069abce7b.mp4",
        ref_file="bc1e9e2a2295c9fd810c45b5495ff3ad7434ae15e1c89b5ff6aa2d32ff7fa52e.png",
        prefix="video/Wan_VACE",
        guide_title="Wan VACE 1.3B / 14B",
        guide=guide("Wan VACE 1.3B / 14B",
                    "배경 확장·교체용 기본 세팅입니다. 마스크(검은 하늘/배경 영역)만 새로 생성하고 인물·지면은 Pixel Lock으로 원본 픽셀을 유지합니다. "
                    "**14B = Canvas 720p ON**, **1.3B = Canvas 720p OFF + 1.3B LoRA**.",
                    4, "`Output Scale` 기본 1.0 = 원본 해상도 그대로 (예: 1920×1080 소스 → 1920×1080 출력)."),
        models_md=models_md(["14B", "1.3B"]),
        structure_md=STRUCTURE.replace("{turbo}", "4"),
        audit=audit("WAN VACE 1.3B/14B (flat graph, 1280×720 fixed canvas, 1920×1080 fixed output)",
                    ["Negative block moved out of the positive prompt into the Negative Prompt field",
                     "Output no longer forced to 1920×1080; mask preview no longer fixed at 24 fps"]),
    ),
    "inpaint": dict(
        out="WAN_VACE_Inpaint_2x_PixelLock_CreatorUI.json",
        unet="wan2.1_vace_14B_fp16.safetensors",
        lora="Wan21_CausVid_14B_T2V_lora_rank32.safetensors",
        lora_strength=0.3, turbo_steps=6, canvas_720p=True, output_scale=2.0, mask_expand=0,
        seed=832378512055965,
        positive="a man running on the fire ", negative=_neg_cn,
        src_file="2a2edf3df3c892673965ac2d85361eaf2a66b2c22979a84627c010da3e2b1080.mp4",
        mask_file="dfc9d159e3e910f33c3721b4e5da03a3036cd7a9d439334f19f9c10fba48cc14.mp4",
        ref_file="8ba050dc1eaf7fdf15740fbeb69db29593f028f58573705c698118d7be20f7ce.png",
        prefix="video/Wan2.1_VACE",
        guide_title="Wan VACE Inpaint — 2× Pixel-Lock",
        guide=guide("Wan VACE Inpaint — 2× Pixel-Lock",
                    "마스크 영역만 VACE로 다시 그리고, 결과를 **원본 × 2** 해상도로 올린 뒤 마스크 밖은 원본(Lanczos 2×) 픽셀로 고정합니다.",
                    6, "`Output Scale` 기본 **2.0** = 원본 × 2 (1.0으로 바꾸면 원본 해상도)."),
        models_md=models_md(["14B"]),
        structure_md=STRUCTURE.replace("{turbo}", "6"),
        audit=audit("WAN VACE inpaint 2× pixel-lock (subgraph, white mask fill, forced 2× output)",
                    ["2× output kept as default via Output Scale 2.0 (now adjustable)",
                     "Removed unused dangling ImageFromBatch node 308"]),
    ),
}
