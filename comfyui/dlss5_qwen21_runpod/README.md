# DLSS5 스타일 실사화 워크플로우 (Qwen-Image 2.1 · RunPod 최고 품질)

그린스크린 위 CG 이미지를 "DLSS 5 ON" 느낌의 실사 사진으로 바꿉니다. 조명, 재질, 크롬 반사, 가죽 질감을 실사처럼 만들고 **형태와 디테일은 그대로 유지**하는 데 초점을 둔 이미지 → 이미지(img2img) 워크플로우입니다.

| 파일 | 용도 |
|---|---|
| `dlss5_qwen21_2k_detail.json` | ComfyUI 워크플로우. 드래그해서 열면 됩니다 |
| `download_models_runpod.sh` | RunPod에 모델 다운로드 |
| `build_workflow.py` | 워크플로우 생성기. 프롬프트나 기본값을 바꿔 다시 생성할 때 사용 |

## 왜 "진짜 DLSS 5"가 아닌가

NVIDIA DLSS 5 Neural Rendering을 ComfyUI에서 직접 돌리는 비공식 노드(`ComfyUI-DLSS5-NR`)가 있지만, **Windows 전용**이고 `nvngx_dlssnr.dll`을 직접 구해야 합니다. RunPod는 Linux 컨테이너라 이 노드를 쓸 수 없습니다. 그래서 DLSS 5 결과물로 학습한 **생성형 LoRA**(Civitai "Qwen 2.1 - DLSS 5 Edit / Slider", 트리거 `dlss5`)로 같은 룩을 재현합니다.

## 파이프라인

```
원본(CG) ─┬─ S1 Resize 약 2MP ─┬─ TextEncodeQwenImage21 (image_1 = 원본)
          │                    └─ VAEEncode ── KSampler S1 (denoise 0.85) ── S1_look 저장
          │                                                   │
          │        S2 Resize 약 4MP (네이티브 2K) ◀────────────┘
          │          ├─ TextEncodeQwenImage21 (image_1 = S1 결과)
          │          └─ VAEEncode ── KSampler S2 (denoise 0.30) ── S2_2K 저장
          │                                                   │
          └─ GetImageSize ──────▶ ImageScale(원본 크기) ◀───────┘ ── plate_match 저장 + 원본 비교
```

- **모델**: `qwen_image_2.1_bf16` + `qwen3vl_8b_bf16`(텍스트 인코더) + `qwen_image_2.1_vae_bf16`. int8이나 fp8 없이 모두 풀정밀도입니다.
- **디테일 고정 방식**: 공식 템플릿은 빈 latent에서 생성을 시작하지만, 이 워크플로우는 원본을 VAE로 인코딩한 latent에서 시작합니다. 그래서 denoise 값으로 원본을 얼마나 지킬지 조절할 수 있습니다.
- **32px 정렬**: `ImageScaleToTotalPixels(resolution_steps=32)`로 미리 맞춰 둡니다. 인코더의 `resolution`이 0이면 입력 크기를 그대로 쓰므로, 레퍼런스 latent와 샘플링 latent의 크기가 정확히 같아집니다. 크기가 다르면 편집 결과가 밀립니다.

## RunPod 세팅

1. **GPU**: 48GB 이상을 권장합니다(L40S, RTX 6000 Ada, A100 80GB, H100). bf16 모델 두 개를 합치면 약 30GB입니다. RTX 4090(24GB)이나 5090(32GB)에서도 돌아가지만, 텍스트 인코더와 DiT를 번갈아 오프로드하므로 느려집니다.
2. **볼륨**: 60GB 이상. 모델만 약 31GB입니다.
3. **ComfyUI 최신화**: Qwen Image 2.1 노드(`TextEncodeQwenImage21`, `QwenImage21Cache`)가 필요합니다. 템플릿마다 경로가 다르니 ComfyUI가 설치된 폴더 기준으로 실행하세요.

   ```bash
   cd /workspace/ComfyUI && git pull && pip install -r requirements.txt
   ```

4. **모델 받기**:

   ```bash
   COMFY_DIR=/workspace/ComfyUI CIVITAI_VERSION_ID=<버전ID> CIVITAI_TOKEN=<토큰> bash download_models_runpod.sh
   ```

   - LoRA는 Civitai 모델 페이지에서 **Edit(img2img) 버전**을 받아야 합니다. 버전 ID는 다운로드 버튼 링크에 있는 숫자입니다.
   - 저장 이름은 `models/loras/qwen21_dlss5_edit.safetensors`입니다. 다른 이름으로 받았다면 LoRA 노드에서 직접 선택하세요.
5. ComfyUI를 재시작하고 `dlss5_qwen21_2k_detail.json`을 열어, `LoadImage`에서 원본 이미지를 선택한 뒤 실행합니다.

## 디테일 노브

| 노브 | 기본값 | 범위 | 효과 |
|---|---|---|---|
| KSampler S1 `denoise` | 0.85 | 0.70~1.00 | 낮출수록 원본 형태와 디테일을 지킴. 1.0이면 공식 순수 편집 |
| KSampler S2 `denoise` | 0.30 | 0.20~0.45 | 높일수록 마이크로 디테일이 늘지만 형태가 바뀔 위험이 커짐 |
| DLSS5 LoRA `strength` | 1.0 | 0.6~1.0 | 슬라이더 LoRA. 0.6~0.8은 은은하게, 1.0은 풀 DLSS5 |
| S2 Resize `megapixels` | 3.9 | ≤ 4.0 | Qwen 2.1의 최대 픽셀 예산은 2048²(4.0MP)이므로 이 이상 올리지 말 것 |
| S1 / S2 `steps` | 50 / 30 | | 공식 권장은 euler 40~50 |

- `cfg`는 1로 둡니다(Qwen 2.1 공식 설정). cfg가 1이면 negative 프롬프트는 무시됩니다.
- 시드는 fixed입니다. S1 룩이 마음에 들면 S1은 그대로 두고 S2만 조절하세요. ComfyUI는 바뀐 노드부터만 다시 계산합니다.
- 공식 프롬프트 인핸서(Qwen3.5 9B)는 넣지 않았습니다. 프롬프트가 이미 구체적인데 인핸서가 이를 다시 쓰면 "형태 유지" 지시가 약해질 수 있기 때문입니다.

## 프롬프트

**S1: 룩 변환**

```
dlss5. Re-render <image1> as a real high-end studio photograph with DLSS 5 style neural rendering. Physically accurate lighting with soft contact shadows under the runners, true mirror-chrome reflections on the scrollwork runners, bumpers and trim, pearlescent white automotive paint with clear-coat highlights, real cream leather seats with visible stitching, piping and natural creases, dark brown leather armrests, glass headlight lenses with warm glowing bulbs and visible reflectors, a polished silver reindeer hood ornament, pale blue gift boxes with satin burgundy ribbons. Keep the exact composition, camera angle, framing, proportions and every curl and ornament detail unchanged; same number of seats and gift boxes. Keep the flat, evenly lit chroma-key green background and floor unchanged, without adding extra green color cast on the white paint or the seats. Crisp sharp edges, rich micro-detail, no blur, no noise.
```

**S2: 2K 디테일 리파인**

```
dlss5. <image1> High-resolution detail refinement of this photograph. Sharpen and enrich fine micro-detail: leather grain and stitching, chrome scrollwork reflections, paint clear-coat, headlight glass and reflectors, satin ribbon weave, reindeer ornament engraving. Keep everything else identical: same composition, shapes, colors, lighting and the flat chroma-key green background. No new objects, no blur, no noise.
```

다른 이미지에 쓸 때는 S1 프롬프트의 재질 묘사 부분(크롬, 가죽, 페인트 등)만 그 이미지에 맞게 바꾸세요. "Keep … unchanged" 문장은 그대로 둡니다.

## After Effects 연결

- `DLSS5/plate_match_*.png`는 원본과 크기가 같습니다. 원본 레이어 위에 그대로 올리면 1:1로 맞습니다. 4MP 결과를 축소한 슈퍼샘플이라 원본보다 선명합니다.
- `DLSS5/S2_2K_*.png`는 32px 정렬 때문에 종횡비가 1~2% 다를 수 있습니다. AE에서 원본 크기 컴프에 놓고 **Fit to Comp(Ctrl+Alt+F)**를 적용하면 정확히 겹칩니다.
- 그린 배경은 프롬프트로 균일하게 유지하도록 지시했지만, 키잉 전에 배경이 고르게 나왔는지 꼭 확인하세요. 크롬에 비친 초록은 실사라면 원래 생기는 반사이므로 Spill 억제로 처리하면 됩니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| 장식 곡선이나 엠블럼 형태가 변함 | S1 denoise를 0.75로 낮추거나 S2 denoise를 0.2로 낮춤 |
| DLSS5 느낌이 약함 | S1 denoise를 0.95~1.0으로 올리고, LoRA strength가 1.0인지 확인 |
| OOM (24~32GB GPU) | `QwenImage21Cache`의 device를 `cpu`로, dtype을 `int8`로 바꿈. 그래도 부족하면 S2 megapixels를 3.0으로 낮춤 |
| 노드가 빨간색(없음) | ComfyUI를 최신으로 업데이트. Qwen Image 2.1 노드는 최신 버전에만 있음 |
| LoRA 없이 테스트하고 싶음 | LoRA 노드를 선택하고 Ctrl+B로 bypass. 프롬프트만으로도 동작하지만 룩이 약해짐 |

## 참고: 로컬 RTX 3060 12GB

모델 파일을 `qwen_image_2.1_int8_convrot` / `qwen3vl_8b_int8_convrot`(각각 6.76GB / 8.71GB)로 바꾸면 3060 12GB에서도 돌아갑니다. ComfyUI의 int8 연산은 CUDA GPU 세대 제한이 없고, 3060(Ampere)이 지원하지 않는 FP8은 쓰지 않습니다. 다만 S2 megapixels는 2.0 이하로 낮추고 시스템 RAM은 32GB 이상을 권장합니다.

## 검증 범위

- 노드 이름, 입출력 슬롯, 위젯 순서는 Comfy-Org 공식 Qwen Image 2.1 편집 템플릿과 ComfyUI 소스(`comfy_extras/nodes_qwen.py`)를 기준으로 맞췄습니다. 링크와 타입 일관성은 `build_workflow.py`가 생성할 때마다 자동으로 검사합니다.
- 실제 GPU에서 이미지를 생성해 보지는 않았습니다. denoise 기본값(0.85 / 0.30)은 출발점이므로 첫 결과를 보고 위 표에 따라 조절하세요.
