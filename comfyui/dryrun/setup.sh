#!/usr/bin/env bash
# Dry-run test bench: real ComfyUI v0.31.1 (CPU) + real frontend + stubbed model math.
# Usage:  bash setup.sh            # install once
#         bash setup.sh serve      # start the server (log -> server.log)
#         python test_anim.py && python test_vace.py
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
COMFY="${COMFY_DIR:-$HERE/ComfyUI}"

if [[ "${1:-}" == "serve" ]]; then
  source "$HERE/.venv/bin/activate"
  cd "$COMFY"
  exec python main.py --cpu --listen 127.0.0.1 --port 8188 --disable-auto-launch > "$HERE/server.log" 2>&1
fi

[[ -d "$COMFY" ]] || git clone --depth 1 --branch v0.31.1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY"
python3 -m venv "$HERE/.venv"
source "$HERE/.venv/bin/activate"
pip install -q torch torchvision torchaudio
pip install -q -r "$COMFY/requirements.txt"

# model math stubs (schemas stay real)
rm -rf "$COMFY/custom_nodes/dryrun_stubs"
cp -r "$HERE/dryrun_stubs" "$COMFY/custom_nodes/dryrun_stubs"

# empty placeholder files so combo validation passes (stubbed loaders never read them)
M="$COMFY/models"
touch "$M/diffusion_models/"{wan_animate_2_int8_convrot,wan_animate_2_distill_int8_convrot,wan2.1_vace_14B_fp16,wan2.1_vace_1.3B_fp16}.safetensors
touch "$M/loras/"{Comfy-Org__Wan-Animate-2__lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16,lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16,Wan21_CausVid_14B_T2V_lora_rank32,Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32}.safetensors
mkdir -p "$M/loras/wan21" && touch "$M/loras/wan21/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
touch "$M/text_encoders/"{umt5_xxl_fp8_e4m3fn_scaled,Comfy-Org__Wan-Animate-2__umt5_xxl_fp8_e4m3fn_scaled}.safetensors
touch "$M/vae/"{wan_2.1_vae,Comfy-Org__Wan-Animate-2__Wan2_1_VAE_bf16}.safetensors
touch "$M/clip_vision/clip_vision_h.safetensors"

# synthetic inputs: frame index encoded as colour (R = i % 16, G = i // 16), moving square, 440 Hz audio
python "$HERE/gen_media.py" "$COMFY/input"

# headless frontend bridge (graphToPrompt) needs Node + Playwright
command -v node >/dev/null || { echo "install Node.js + 'npm i -g playwright'"; exit 1; }
echo "ready: bash setup.sh serve  (then run the tests in another shell)"
