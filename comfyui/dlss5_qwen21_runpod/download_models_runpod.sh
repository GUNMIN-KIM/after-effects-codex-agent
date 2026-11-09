#!/usr/bin/env bash
# RunPod: Qwen-Image 2.1 (bf16 풀정밀도) + DLSS5 Edit LoRA 모델 다운로드
#
# 사용법:
#   COMFY_DIR=/workspace/ComfyUI bash download_models_runpod.sh
#   LoRA까지 받으려면 (Civitai 다운로드 버튼 링크의 숫자 = 버전 ID):
#   CIVITAI_VERSION_ID=123456 CIVITAI_TOKEN=xxxx bash download_models_runpod.sh
#
# 총 용량 약 31GB 이상 → 네트워크 볼륨은 60GB 이상을 권장합니다.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
HF_BASE="https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main"

if [ ! -d "$COMFY_DIR/models" ]; then
  echo "ComfyUI 폴더를 찾을 수 없음: $COMFY_DIR (COMFY_DIR=... 로 지정하세요)" >&2
  exit 1
fi

dl() { # dl <url> <dest> [extra curl args...]
  local url="$1" dest="$2"; shift 2
  if [ -s "$dest" ]; then echo "skip (이미 있음): $dest"; return 0; fi
  mkdir -p "$(dirname "$dest")"
  echo "download: $dest"
  curl -fL --retry 5 --retry-delay 5 -C - "$@" -o "$dest.part" "$url"
  mv "$dest.part" "$dest"
}

dl "$HF_BASE/diffusion_models/qwen_image_2.1_bf16.safetensors" \
   "$COMFY_DIR/models/diffusion_models/qwen_image_2.1_bf16.safetensors"
dl "$HF_BASE/text_encoders/qwen3vl_8b_bf16.safetensors" \
   "$COMFY_DIR/models/text_encoders/qwen3vl_8b_bf16.safetensors"
dl "$HF_BASE/vae/qwen_image_2.1_vae_bf16.safetensors" \
   "$COMFY_DIR/models/vae/qwen_image_2.1_vae_bf16.safetensors"

# DLSS5 Edit LoRA (Civitai: "Qwen 2.1 - DLSS 5 Edit / Slider" → Edit 버전)
if [ -n "${CIVITAI_VERSION_ID:-}" ] && [ -n "${CIVITAI_TOKEN:-}" ]; then
  dl "https://civitai.com/api/download/models/${CIVITAI_VERSION_ID}" \
     "$COMFY_DIR/models/loras/qwen21_dlss5_edit.safetensors" \
     -H "Authorization: Bearer ${CIVITAI_TOKEN}"
else
  echo "LoRA 건너뜀: CIVITAI_VERSION_ID / CIVITAI_TOKEN 미설정."
  echo "  → Civitai에서 Edit 버전을 받아 $COMFY_DIR/models/loras/qwen21_dlss5_edit.safetensors 로 저장하세요."
fi

echo "완료. ComfyUI를 재시작한 뒤 dlss5_qwen21_2k_detail.json을 드래그해 여세요."
