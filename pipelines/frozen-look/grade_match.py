#!/usr/bin/env python3
"""레퍼런스 룩(떼깔) 매칭 그레이드.

AI 편집 결과는 컷마다 색온도·블랙 레벨·채도가 조금씩 흔들린다. 이 스크립트는
레퍼런스 이미지(완성본 3장)의 톤 분포를 측정해 각 프레임을 그 쪽으로 당긴다.

- L(밝기): 퍼센타일 기준점(p0.5/p5/p50/p95/p99.5)을 레퍼런스에 맞춘 단조 커브
  → 밀키하게 들린 블랙, 낮은 콘트라스트, 크림톤 하이라이트
- a/b(색): 평균(캐스트)과 표준편차(채도)를 레퍼런스에 맞춤 (Reinhard 방식)
- strength로 원본과 블렌드 (기본 0.6). 1.0은 통계를 그대로 강제한다.

의존성: Pillow, numpy (ComfyUI 포터블 python_embeded에 이미 포함)

예시:
  python grade_match.py --in out/raw --out out/graded --ref reference/ref_1.webp
  python grade_match.py --in shot.png --out graded --ref reference --strength 0.5 --report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
PCTS = (0.5, 5.0, 50.0, 95.0, 99.5)

# ---------------------------------------------------------------- color math
_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]], dtype=np.float64)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb: float array [...,3] in 0..1 (sRGB) -> Lab (L 0..100)."""
    xyz = _srgb_to_linear(rgb) @ _M_RGB2XYZ.T / _WHITE
    e, k = 216 / 24389, 24389 / 27
    f = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    e, k = 216 / 24389, 24389 / 27
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f ** 3 > e, f ** 3, (116 * f - 16) / k)
    xyz[..., 1] = np.where(L > k * e, ((L + 16) / 116) ** 3, L / k)
    rgb_lin = (xyz * _WHITE) @ _M_XYZ2RGB.T
    return np.clip(_linear_to_srgb(rgb_lin), 0.0, 1.0)


# ---------------------------------------------------------------- stats
def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0


def _thumb_lab(path: Path, max_side: int = 640) -> np.ndarray:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        rgb = np.asarray(im, dtype=np.float64) / 255.0
    return rgb_to_lab(rgb).reshape(-1, 3)


def lab_stats(lab_pixels: np.ndarray) -> dict:
    L = lab_pixels[:, 0]
    return {
        "L_pct": np.percentile(L, PCTS),
        "ab_mean": lab_pixels[:, 1:].mean(axis=0),
        "ab_std": lab_pixels[:, 1:].std(axis=0) + 1e-6,
    }


def list_images(p: Path) -> list[Path]:
    if p.is_file():
        return [p]
    return sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)


def reference_stats(refs: list[Path]) -> dict:
    """여러 레퍼런스를 합쳐(pooled) 하나의 타깃 통계를 만든다."""
    if not refs:
        raise ValueError("레퍼런스 이미지가 없습니다.")
    pix = np.concatenate([_thumb_lab(r) for r in refs], axis=0)
    return lab_stats(pix)


# ---------------------------------------------------------------- grade
def _tone_curve(L: np.ndarray, src_pct: np.ndarray, tgt_pct: np.ndarray,
                min_gap: float = 1.0) -> np.ndarray:
    # 클리핑된 블랙/화이트처럼 퍼센타일이 겹치면 기준점을 건너뛴다 (섀도 단절·포스터라이즈 방지)
    xs: list[float] = []
    ys: list[float] = []
    for s, t in zip(src_pct, tgt_pct):
        if xs and s - xs[-1] < min_gap:
            continue
        xs.append(float(s))
        ys.append(float(t))
    if xs[0] > 1e-3:  # 첫 기준점 아래는 기울기 1로 연장
        xs.insert(0, 0.0)
        ys.insert(0, max(0.0, ys[0] - xs[1]))
    if xs[-1] < 100.0 - 1e-3:  # 마지막 기준점 위도 기울기 1로 연장
        ys.append(min(100.0, ys[-1] + (100.0 - xs[-1])))
        xs.append(100.0)
    ys_arr = np.maximum.accumulate(np.asarray(ys))  # 단조 증가 → 톤 반전 없음
    return np.interp(L, np.asarray(xs), ys_arr)


def apply_look(rgb: np.ndarray, target: dict, strength: float = 0.6,
               chroma_ratio_clamp: tuple[float, float] = (0.55, 1.4),
               grain: float = 0.0, seed: int = 0) -> np.ndarray:
    """rgb 0..1 → rgb 0..1. target은 reference_stats() 결과."""
    lab = rgb_to_lab(rgb)
    src = lab_stats(lab.reshape(-1, 3))
    s = float(np.clip(strength, 0.0, 1.0))

    L = lab[..., 0]
    L_new = _tone_curve(L, src["L_pct"], target["L_pct"])
    lab[..., 0] = L + s * (L_new - L)

    ratio = np.clip(target["ab_std"] / src["ab_std"], *chroma_ratio_clamp)
    for i, ch in enumerate((1, 2)):
        c = lab[..., ch]
        c_new = (c - src["ab_mean"][i]) * ratio[i] + target["ab_mean"][i]
        lab[..., ch] = c + s * (c_new - c)

    out = lab_to_rgb(lab)
    if grain > 0:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, grain, size=out.shape[:2])[..., None]
        out = np.clip(out + noise, 0.0, 1.0)
    return out


def save_rgb(rgb: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(path)


def describe(name: str, st: dict) -> str:
    Lp = ", ".join(f"{v:5.1f}" for v in st["L_pct"])
    return (f"{name:<28} L[p0.5,p5,p50,p95,p99.5]=[{Lp}]  "
            f"a/b mean=({st['ab_mean'][0]:+5.2f},{st['ab_mean'][1]:+5.2f})  "
            f"a/b std=({st['ab_std'][0]:4.2f},{st['ab_std'][1]:4.2f})")


def grade_file(src: Path, dst: Path, target: dict, strength: float, grain: float,
               report: bool = False) -> None:
    rgb = load_rgb(src)
    out = apply_look(rgb, target, strength=strength, grain=grain,
                     seed=abs(hash(src.name)) % (2 ** 32))
    save_rgb(out, dst)
    if report:
        print(describe(f"  before {src.name[:20]}", lab_stats(rgb_to_lab(rgb).reshape(-1, 3))))
        print(describe(f"  after  {dst.name[:20]}", lab_stats(rgb_to_lab(out).reshape(-1, 3))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="레퍼런스 룩 매칭 그레이드 (Lab 톤커브 + Reinhard 색 전송)")
    ap.add_argument("--in", dest="inp", required=True, help="입력 이미지 파일 또는 폴더")
    ap.add_argument("--out", required=True, help="출력 폴더 (입력 폴더와 달라야 함)")
    ap.add_argument("--ref", required=True, nargs="+", help="레퍼런스 이미지 파일들 또는 폴더")
    ap.add_argument("--strength", type=float, default=0.6, help="0~1, 기본 0.6")
    ap.add_argument("--grain", type=float, default=0.0, help="필름 그레인 σ (0~0.03 권장, 기본 0)")
    ap.add_argument("--suffix", default="", help="출력 파일명 접미사 (예: _graded)")
    ap.add_argument("--report", action="store_true", help="전/후 통계 출력")
    a = ap.parse_args(argv)

    inp, out_dir = Path(a.inp), Path(a.out)
    refs: list[Path] = []
    for r in a.ref:
        refs += list_images(Path(r))
    target = reference_stats(refs)
    print(describe("TARGET (refs pooled)", target))

    files = list_images(inp)
    if not files:
        print("입력 이미지가 없습니다.", file=sys.stderr)
        return 1
    if inp.is_dir() and out_dir.resolve() == inp.resolve():
        print("출력 폴더는 입력 폴더와 달라야 합니다 (원본 보호).", file=sys.stderr)
        return 2
    for f in files:
        dst = out_dir / f"{f.stem}{a.suffix}.png"
        grade_file(f, dst, target, a.strength, a.grain, a.report)
        print(f"graded: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
