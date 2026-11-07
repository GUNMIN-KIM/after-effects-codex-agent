#!/usr/bin/env python3
"""컷별 프레임 폴더 → '얼어붙은 실내' 룩 일괄 변환 (ComfyUI API + Qwen-Image-Edit-2511).

흐름 (프레임마다):
  원본 로드 → ~1MP(16배수)로 축소 → ComfyUI 업로드 → 편집(프롬프트+룩 레퍼런스)
  → 결과 다운로드 → 원본 해상도로 복원 → 레퍼런스 룩 그레이드 → 저장
마지막에 원본|결과 컨택트 시트와 log.jsonl을 만든다. 원본 폴더는 절대 수정하지 않는다.

의존성: Python 3.9+, Pillow, numpy (ComfyUI 포터블의 python_embeded에 포함). 표준 urllib만 사용.

예시 (Windows, ComfyUI가 http://127.0.0.1:8188 에서 실행 중):
  python batch_freeze.py --in "C:\\Users\\me\\Desktop\\프로젝트\\니쥬\\소스_2\\01_컷별\\프레임" --init-shots shots.csv
  python batch_freeze.py --in "...\\프레임" --out "...\\프레임_frozen" --refs reference --shots shots.csv
  python batch_freeze.py --in "...\\프레임" --out "...\\프레임_frozen" --refs reference --dry-run
"""
from __future__ import annotations

import argparse
import copy
import csv
import glob
import hashlib
import io
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grade_match  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
SHOT_TYPES = ("cu", "ms", "ws", "walk")
DEFAULT_TEMPLATE = HERE / "workflows" / "qwen2511_frozen_edit_api.json"
DEFAULT_PROMPTS = HERE / "prompts.json"

# 템플릿 노드 ID (workflows/qwen2511_frozen_edit_api.json 과 일치해야 함)
N_CLIP, N_UNET, N_VAE, N_SHIFT, N_CFGNORM = "1", "2", "3", "4", "5"
N_SRC, N_REF, N_SRC_SCALE, N_REF_SCALE = "10", "11", "12", "13"
N_POS, N_NEG, N_SAMPLER, N_DECODE, N_SAVE = "20", "21", "31", "32", "40"
N_LORA, N_UPSCALE_LOADER, N_UPSCALE = "50", "60", "61"


# ---------------------------------------------------------------- data
@dataclass
class Shot:
    file: str
    shot: str = "ms"
    ref: str = "1"           # 1/2/3 (reference 폴더 정렬 순서) | 파일 경로 | none
    extra: str = ""          # 이 컷에만 추가할 프롬프트 (영문 권장)
    seed: int | None = None
    variants: int | None = None
    skip: bool = False


@dataclass
class Settings:
    unet: str
    clip: str
    vae: str
    lora: str | None
    lora_strength: float
    steps: int
    cfg: float
    shift: float
    megapixels: float
    upscale_model: str | None
    sampler: str = "euler"
    scheduler: str = "simple"
    extra_global: str = ""
    use_negative: bool = True
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------- helpers
def list_images(folder: Path) -> list[Path]:
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)


def edit_size(w: int, h: int, megapixels: float = 1.0, step: int = 16) -> tuple[int, int]:
    """ImageScaleToTotalPixels(megapixels, resolution_steps=16)와 같은 공식."""
    scale = math.sqrt(megapixels * 1024 * 1024 / (w * h))
    return max(step, round(w * scale / step) * step), max(step, round(h * scale / step) * step)


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def read_shots(path: Path | None) -> dict[str, Shot]:
    if not path or not path.exists():
        return {}
    shots: dict[str, Shot] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:  # 엑셀 저장 CSV(BOM) 대응
        for row in csv.DictReader(f):
            name = (row.get("file") or "").strip()
            if not name or name.startswith("#"):
                continue
            shot = (row.get("shot") or "ms").strip().lower()
            if shot not in SHOT_TYPES:
                raise SystemExit(f"[shots] {name}: shot='{shot}' 는 {SHOT_TYPES} 중 하나여야 합니다.")
            seed = (row.get("seed") or "").strip()
            variants = (row.get("variants") or "").strip()
            shots[name] = Shot(
                file=name,
                shot=shot,
                ref=(row.get("ref") or "1").strip() or "1",
                extra=(row.get("extra") or "").strip(),
                seed=int(seed) if seed else None,
                variants=int(variants) if variants else None,
                skip=(row.get("skip") or "").strip().lower() in ("1", "y", "yes", "true", "o", "skip"),
            )
    return shots


def write_shots_template(frames: list[Path], path: Path) -> None:
    if path.exists():
        raise SystemExit(f"{path} 가 이미 있습니다. 덮어쓰지 않습니다.")
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "shot", "ref", "skip", "seed", "variants", "extra"])
        for p in frames:
            w.writerow([p.name, "ms", "1", "", "", "", ""])
    print(f"샷 목록 생성: {path}  ({len(frames)}개)")
    print("shot: cu=클로즈업 / ms=미디엄 / ws=와이드 / walk=복도·걷기, ref: 1·2·3 또는 none, "
          "이미 완성된 3장은 skip=1")


def build_prompt(prompts: dict, shot: Shot, has_ref: bool, extra_global: str) -> str:
    parts = [
        prompts["base_with_ref"] if has_ref else prompts["base_no_ref"],
        prompts["frost"],
        prompts["shots"][shot.shot],
        prompts["look"],
    ]
    if extra_global:
        parts.append(extra_global)
    if shot.extra:
        parts.append(shot.extra)
    return " ".join(p.strip() for p in parts if p.strip())


def build_graph(template: dict, s: Settings, src_name: str, ref_name: str | None,
                positive: str, negative: str, seed: int, prefix: str) -> dict:
    g = copy.deepcopy(template)
    g[N_UNET]["inputs"]["unet_name"] = s.unet
    g[N_CLIP]["inputs"]["clip_name"] = s.clip
    g[N_VAE]["inputs"]["vae_name"] = s.vae
    g[N_SHIFT]["inputs"]["shift"] = s.shift
    g[N_SRC]["inputs"]["image"] = src_name
    g[N_SRC_SCALE]["inputs"]["megapixels"] = s.megapixels
    g[N_REF_SCALE]["inputs"]["megapixels"] = s.megapixels
    g[N_POS]["inputs"]["prompt"] = positive
    g[N_NEG]["inputs"]["prompt"] = negative if s.use_negative else ""

    if ref_name:
        g[N_REF]["inputs"]["image"] = ref_name
    else:  # 레퍼런스 없이 텍스트만으로 편집
        for nid in (N_REF, N_REF_SCALE):
            g.pop(nid, None)
        for nid in (N_POS, N_NEG):
            g[nid]["inputs"].pop("image2", None)

    if s.lora:  # 예: Lightning 4-step LoRA → steps 4, cfg 1
        g[N_LORA] = {
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "LoRA"},
            "inputs": {"model": [N_UNET, 0], "lora_name": s.lora, "strength_model": s.lora_strength},
        }
        g[N_SHIFT]["inputs"]["model"] = [N_LORA, 0]

    k = g[N_SAMPLER]["inputs"]
    k.update(seed=int(seed), steps=s.steps, cfg=s.cfg, sampler_name=s.sampler, scheduler=s.scheduler)

    if s.upscale_model:
        g[N_UPSCALE_LOADER] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": s.upscale_model}}
        g[N_UPSCALE] = {"class_type": "ImageUpscaleWithModel",
                        "inputs": {"upscale_model": [N_UPSCALE_LOADER, 0], "image": [N_DECODE, 0]}}
        g[N_SAVE]["inputs"]["images"] = [N_UPSCALE, 0]

    g[N_SAVE]["inputs"]["filename_prefix"] = prefix
    return g


# ---------------------------------------------------------------- ComfyUI client
class Comfy:
    def __init__(self, server: str, timeout: float):
        self.base = server.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    def _req(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"ComfyUI {method} {path} → HTTP {e.code}: {body[:2000]}") from None

    def ping(self) -> dict:
        return json.loads(self._req("GET", "/system_stats"))

    def upload(self, png: bytes, name: str) -> str:
        boundary = "----frozenlook" + uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n".encode(),
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
             f"Content-Type: image/png\r\n\r\n").encode() + png + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(parts)
        res = json.loads(self._req("POST", "/upload/image", body,
                                   {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
        sub = res.get("subfolder") or ""
        return f"{sub}/{res['name']}" if sub else res["name"]

    def queue(self, graph: dict) -> str:
        body = json.dumps({"prompt": graph, "client_id": self.client_id}).encode("utf-8")
        res = json.loads(self._req("POST", "/prompt", body, {"Content-Type": "application/json"}))
        if res.get("node_errors"):
            raise RuntimeError(f"노드 오류: {json.dumps(res['node_errors'], ensure_ascii=False)[:2000]}")
        return res["prompt_id"]

    def wait(self, prompt_id: str, poll: float = 1.5) -> dict:
        t0 = time.time()
        while True:
            hist = json.loads(self._req("GET", f"/history/{prompt_id}"))
            if prompt_id in hist:
                item = hist[prompt_id]
                status = item.get("status", {})
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    raise RuntimeError(f"실행 오류: {json.dumps(msgs, ensure_ascii=False)[:2000]}")
                if item.get("outputs") or status.get("completed"):
                    return item
            if time.time() - t0 > self.timeout:
                raise TimeoutError(f"{prompt_id}: {self.timeout:.0f}s 안에 끝나지 않았습니다.")
            time.sleep(poll)

    def fetch_output(self, item: dict, node_id: str) -> Image.Image:
        images = item.get("outputs", {}).get(node_id, {}).get("images", [])
        if not images:
            raise RuntimeError(f"SaveImage({node_id}) 출력이 없습니다.")
        im = images[0]
        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                    "type": im.get("type", "output")})
        data = self._req("GET", f"/view?{q}")
        return Image.open(io.BytesIO(data)).convert("RGB")


# ---------------------------------------------------------------- contact sheet
def contact_sheet(rows: list[tuple[Path, list[Path]]], dst: Path, cell_w: int = 480) -> None:
    if not rows:
        return
    cols = 1 + max(len(r[1]) for r in rows)
    tiles = []
    for src, outs in rows:
        with Image.open(src) as im:
            row_h = round(im.height * cell_w / im.width)  # 행 높이는 원본 비율 기준 (세로 컷 대응)
        row = []
        for p in [src] + outs:
            with Image.open(p) as im:
                row.append(im.convert("RGB").resize((cell_w, row_h), Image.LANCZOS))
        tiles.append(row)
    sheet = Image.new("RGB", (cols * cell_w, sum(r[0].height for r in tiles)), (16, 16, 16))
    y = 0
    for row in tiles:
        for x, t in enumerate(row):
            sheet.paste(t, (x * cell_w, y))
        y += row[0].height
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, quality=88)


# ---------------------------------------------------------------- main
def resolve_ref(shot: Shot, refs: list[Path], no_ref: bool) -> Path | None:
    if no_ref or shot.ref.lower() == "none":
        return None
    if shot.ref.isdigit():
        i = int(shot.ref) - 1
        if not refs:
            raise SystemExit("--refs 폴더에 레퍼런스 이미지가 없습니다. (또는 --no-ref)")
        if not 0 <= i < len(refs):
            raise SystemExit(f"[{shot.file}] ref={shot.ref}: 레퍼런스는 1~{len(refs)} 입니다.")
        return refs[i]
    p = Path(shot.ref)
    if not p.exists():
        raise SystemExit(f"[{shot.file}] 레퍼런스 파일 없음: {p}")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="컷별 프레임 → 얼어붙은 실내 룩 일괄 변환 (ComfyUI)")
    ap.add_argument("--in", dest="inp", required=True, help="원본 프레임 폴더 (읽기 전용으로 취급)")
    ap.add_argument("--out", help="결과 폴더 (기본: <입력>_frozen)")
    ap.add_argument("--refs", default=str(HERE / "reference"), help="룩 레퍼런스 폴더 (완성본 3장)")
    ap.add_argument("--shots", help="컷별 설정 CSV (file,shot,ref,skip,seed,variants,extra)")
    ap.add_argument("--init-shots", metavar="CSV", help="입력 폴더를 훑어 shots CSV 템플릿만 만들고 종료")
    ap.add_argument("--only", help="쉼표로 구분한 파일명만 처리")
    ap.add_argument("--skip", help="쉼표로 구분한 파일명 건너뛰기 (이미 완성된 컷)")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    ap.add_argument("--unet", default="qwen_image_edit_2511_bf16.safetensors")
    ap.add_argument("--clip", default="qwen_2.5_vl_7b_fp8_scaled.safetensors")
    ap.add_argument("--vae", default="qwen_image_vae.safetensors")
    ap.add_argument("--lora", help="예: Lightning 4-step LoRA 파일명 (사용 시 --steps 4 --cfg 1)")
    ap.add_argument("--lora-strength", type=float, default=1.0)
    ap.add_argument("--steps", type=int, default=20, help="기본 20 (품질 우선 40)")
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--shift", type=float, default=3.1)
    ap.add_argument("--mp", type=float, default=1.0, help="편집 해상도(메가픽셀). 1.0 권장")
    ap.add_argument("--upscale-model", help="예: 4x-UltraSharp.pth (models/upscale_models). 없으면 Lanczos")
    ap.add_argument("--variants", type=int, default=2, help="컷당 시드 후보 수 (기본 2)")
    ap.add_argument("--seed", type=int, default=20261107, help="기본 시드 (컷마다 파일명 해시가 더해짐)")
    ap.add_argument("--no-ref", action="store_true", help="레퍼런스 이미지 없이 텍스트로만 편집")
    ap.add_argument("--extra", default="", help="모든 컷에 추가할 프롬프트")
    ap.add_argument("--grade-strength", type=float, default=0.6, help="룩 그레이드 강도 0~1 (0=끔)")
    ap.add_argument("--grain", type=float, default=0.0, help="그레인 σ (0~0.03)")
    ap.add_argument("--timeout", type=float, default=900, help="컷당 최대 대기(초)")
    ap.add_argument("--force", action="store_true", help="이미 있는 결과도 다시 생성")
    ap.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 계획/그래프만 출력")
    a = ap.parse_args(argv)

    inp = Path(a.inp)
    if not inp.is_dir():
        raise SystemExit(f"입력 폴더가 없습니다: {inp}")
    frames = list_images(inp)
    if a.init_shots:
        write_shots_template(frames, Path(a.init_shots))
        return 0

    out = Path(a.out) if a.out else inp.with_name(inp.name + "_frozen")
    if out.resolve() == inp.resolve() or inp.resolve() in out.resolve().parents:
        raise SystemExit("출력 폴더는 입력 폴더 밖이어야 합니다 (원본 보호).")

    prompts = json.loads(Path(a.prompts).read_text(encoding="utf-8"))
    template = json.loads(Path(a.template).read_text(encoding="utf-8"))
    refs_dir = Path(a.refs)
    refs = list_images(refs_dir) if refs_dir.is_dir() else []
    shots = read_shots(Path(a.shots) if a.shots else None)
    only = {s.strip() for s in a.only.split(",")} if a.only else None
    skip = {s.strip() for s in a.skip.split(",")} if a.skip else set()

    s = Settings(unet=a.unet, clip=a.clip, vae=a.vae, lora=a.lora, lora_strength=a.lora_strength,
                 steps=a.steps, cfg=a.cfg, shift=a.shift, megapixels=a.mp,
                 upscale_model=a.upscale_model, extra_global=a.extra, use_negative=a.cfg > 1.0)

    # 계획표
    plan = []
    for f in frames:
        sh = shots.get(f.name, Shot(file=f.name))
        if (only and f.name not in only) or f.name in skip or sh.skip:
            continue
        plan.append((f, sh, resolve_ref(sh, refs, a.no_ref)))
    print(f"입력 {len(frames)}장 / 처리 {len(plan)}장 → {out}")
    print(f"레퍼런스: {[r.name for r in refs] or '없음'}  모델: {s.unet}  steps={s.steps} cfg={s.cfg}"
          f"{'  LoRA=' + s.lora if s.lora else ''}")
    for f, sh, ref in plan:
        print(f"  - {f.name:<40} shot={sh.shot:<4} ref={ref.name if ref else 'none'}"
              f"{'  +extra' if sh.extra else ''}")
    if not plan:
        return 0

    target_cache: dict[str, dict] = {}
    pooled = grade_match.reference_stats(refs) if refs else None

    def grade_target(ref: Path | None) -> dict | None:
        # 컷이 쓴 레퍼런스 70% + 3장 평균 30% → 컷 성격은 살리고 시퀀스 톤은 통일
        if not refs:
            return None
        if ref is None:
            return pooled
        key = str(ref)
        if key not in target_cache:
            one = grade_match.reference_stats([ref])
            target_cache[key] = {k: 0.7 * one[k] + 0.3 * pooled[k] for k in one}
        return target_cache[key]

    if a.dry_run:
        f, sh, ref = plan[0]
        g = build_graph(template, s, "SOURCE.png", "REF.png" if ref else None,
                        build_prompt(prompts, sh, ref is not None, s.extra_global),
                        prompts["negative"], a.seed, "frozen_look/dry")
        print("\n[dry-run] 첫 컷 그래프:\n" + json.dumps(g, ensure_ascii=False, indent=1))
        return 0

    comfy = Comfy(a.server, a.timeout)
    try:
        comfy.ping()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"ComfyUI 연결 실패 ({a.server}): {e}\nComfyUI를 먼저 실행하세요.")

    (out / "raw").mkdir(parents=True, exist_ok=True)
    log_path = out / "log.jsonl"
    uploaded_refs: dict[str, str] = {}
    sheet_rows: list[tuple[Path, list[Path]]] = []
    failures = []
    done = 0

    for idx, (f, sh, ref) in enumerate(plan, 1):
        with Image.open(f) as im:
            src = im.convert("RGB")
        W, H = src.size
        ew, eh = edit_size(W, H, s.megapixels)
        tag = hashlib.sha1(f.name.encode("utf-8")).hexdigest()[:8]
        n_var = sh.variants or a.variants
        base_seed = sh.seed if sh.seed is not None else a.seed + int(tag, 16) % 100000
        outs: list[Path] = []
        print(f"\n[{idx}/{len(plan)}] {f.name}  {W}x{H} → edit {ew}x{eh}  variants={n_var}")
        try:
            src_name = comfy.upload(to_png_bytes(src.resize((ew, eh), Image.LANCZOS)), f"frz_{tag}.png")
            ref_name = None
            if ref is not None:
                key = str(ref)
                if key not in uploaded_refs:
                    with Image.open(ref) as rim:
                        rim = rim.convert("RGB")
                        rw, rh = edit_size(*rim.size, s.megapixels)
                        rtag = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
                        uploaded_refs[key] = comfy.upload(to_png_bytes(rim.resize((rw, rh), Image.LANCZOS)),
                                                          f"frzref_{rtag}.png")
                ref_name = uploaded_refs[key]
            positive = build_prompt(prompts, sh, ref is not None, s.extra_global)

            for v in range(n_var):
                stem = f"{f.stem}_frz_v{v + 1:02d}"
                final_path = out / f"{stem}.png"
                if final_path.exists() and not a.force:
                    print(f"  v{v + 1:02d} 이미 있음 → 건너뜀")
                    outs.append(final_path)
                    continue
                seed = base_seed + v
                g = build_graph(template, s, src_name, ref_name, positive, prompts["negative"],
                                seed, f"frozen_look/{f.stem}_v{v + 1:02d}")
                t0 = time.time()
                pid = comfy.queue(g)
                item = comfy.wait(pid)
                res = comfy.fetch_output(item, N_SAVE)
                res = res.resize((W, H), Image.LANCZOS)  # 원본 해상도·비율로 복원
                raw_path = out / "raw" / f"{stem}.png"
                res.save(raw_path)
                tgt = grade_target(ref)
                if tgt is not None and a.grade_strength > 0:
                    grade_match.grade_file(raw_path, final_path, tgt, a.grade_strength, a.grain)
                else:
                    res.save(final_path)
                outs.append(final_path)
                dt = time.time() - t0
                print(f"  v{v + 1:02d} seed={seed}  {dt:5.1f}s → {final_path.name}")
                with log_path.open("a", encoding="utf-8") as lf:
                    lf.write(json.dumps({
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"), "source": str(f), "output": str(final_path),
                        "raw": str(raw_path), "shot": sh.shot, "ref": str(ref) if ref else None,
                        "seed": seed, "steps": s.steps, "cfg": s.cfg, "lora": s.lora, "unet": s.unet,
                        "edit_size": [ew, eh], "grade_strength": a.grade_strength,
                        "prompt": positive, "prompt_id": pid, "seconds": round(dt, 1),
                    }, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001  한 컷 실패가 전체를 멈추지 않게
            print(f"  ✗ 실패: {e}")
            failures.append((f.name, str(e)))
        if outs:
            done += 1

    # 컨택트 시트는 이번 실행분이 아니라 출력 폴더에 있는 전체 결과로 만든다 (--only 재실행 대응)
    for f in frames:
        outs = sorted(out.glob(f"{glob.escape(f.stem)}_frz_v*.png"))
        if outs:
            sheet_rows.append((f, outs))
    contact_sheet(sheet_rows, out / "_contact_sheet.jpg")
    print(f"\n완료: {done}컷 / 실패 {len(failures)}컷  → {out}")
    if sheet_rows:
        print(f"검수용 컨택트 시트: {out / '_contact_sheet.jpg'}  (왼쪽=원본, 오른쪽=후보)")
    for name, err in failures:
        print(f"  ✗ {name}: {err[:300]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
