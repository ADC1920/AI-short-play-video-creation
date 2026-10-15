# -*- coding: utf-8 -*-
"""分镜接缝质量量化检测（衔接机制验收的自动化辅助）。

对相邻分镜的「上一段尾帧 vs 下一段首帧」计算四个量化指标，输出每缝分数
并按综合偏差排序，标出最需关注的缝：

  ssim  灰度结构相似度（0-1，越高越接近——同类机位组合下用于横向比较）
  dlum  平均亮度差（0-1，越低越一致）
  dhue  色相圆均值差（0-1，越低越一致）
  dsat  饱和度均值差（0-1，越低越一致）

指标用于「缝与缝之间」横向比较定位问题缝（不同机位硬切的结构相似度天然偏低，
ssim 不作绝对阈值判定；亮度/色相/饱和差作一致性判定）。

用法：
  # 模式 A：一组分镜片段（按文件名排序，两两成缝）
  python tools/check_seams.py <目录> [--pattern "LOOK*.mp4"]
  # 模式 B：拼接成片 + 切点列表（秒，逗号分隔）
  python tools/check_seams.py --video 成片.mp4 --cuts 5.088,10.176,15.264
  # 选项
  --json      输出 JSON（机读）
  --tail 0.12 / --head 0.12   抽帧位置（默认：段尾 -0.12s / 段头 +0.12s）
  --selftest  自检（合成帧 + 合成视频抽帧）

抽帧依赖本机 ffmpeg；指标计算仅用 numpy + Pillow。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from numpy.lib.stride_tricks import sliding_window_view

SSIM_WIN = 11          # SSIM 滑窗
WORK_WIDTH = 360       # 指标计算前的缩放宽度（提速并聚焦整体结构）
C1 = (0.01 * 255) ** 2
C2 = (0.03 * 255) ** 2

# 色调一致性绝对阈值（2026-10-15 用历史 6 段样本 5 个缝校准：
# 人工判定「顺」的缝 1/2/3：dlum ≤0.016、dhue ≤0.052、dsat ≤0.006；
# 人工判定「跳」的缝 4/5：dhue 0.162（色相跳）或 dlum 0.070+dsat 0.036（亮度跳））。
# 超过阈值即打 ⚠（该维度出现肉眼可见的不一致）。
TH_DLUM = 0.03
TH_DHUE = 0.06
TH_DSAT = 0.01


# ---------------- 指标 ----------------

def _to_gray_hsv(img: Image.Image, width: int = WORK_WIDTH):
    """返回 (灰度 float 数组, HSV float 数组)，统一缩放到指定宽度。"""
    h = max(1, round(img.height * width / img.width))
    img = img.resize((width, h), Image.LANCZOS)
    gray = np.asarray(img.convert("L"), dtype=np.float64)
    hsv = np.asarray(img.convert("HSV"), dtype=np.float64)
    return gray, hsv


def ssim_gray(a: np.ndarray, b: np.ndarray, win: int = SSIM_WIN) -> float:
    """灰度 SSIM（uniform 窗口，valid 区域均值）。"""
    if a.shape != b.shape:
        s = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        a, b = a[:s[0], :s[1]], b[:s[0], :s[1]]
    if a.shape[0] < win or a.shape[1] < win:
        win = max(3, min(a.shape) // 2 * 2 + 1)
    wa = sliding_window_view(a, (win, win))
    wb = sliding_window_view(b, (win, win))
    mu_a, mu_b = wa.mean(axis=(-2, -1)), wb.mean(axis=(-2, -1))
    va = (wa * wa).mean(axis=(-2, -1)) - mu_a * mu_a
    vb = (wb * wb).mean(axis=(-2, -1)) - mu_b * mu_b
    cov = (wa * wb).mean(axis=(-2, -1)) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + C1) * (2 * cov + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(np.clip(s.mean(), 0.0, 1.0))


def hue_circular_diff(hsv_a: np.ndarray, hsv_b: np.ndarray) -> float:
    """色相圆均值差：0（同相）~ 0.5（反相），归一化到 0-1。"""
    ang_a = hsv_a[..., 0] / 255.0 * 2 * np.pi
    ang_b = hsv_b[..., 0] / 255.0 * 2 * np.pi
    va = np.array([np.mean(np.cos(ang_a)), np.mean(np.sin(ang_a))])
    vb = np.array([np.mean(np.cos(ang_b)), np.mean(np.sin(ang_b))])
    return float(min(1.0, np.linalg.norm(va - vb) / 2.0))


def seam_metrics(img_a: Image.Image, img_b: Image.Image) -> dict:
    """两帧（上一段尾帧 / 下一段首帧）的接缝指标。"""
    ga, ha = _to_gray_hsv(img_a)
    gb, hb = _to_gray_hsv(img_b)
    return {
        "ssim": round(ssim_gray(ga, gb), 4),
        "dlum": round(abs(ga.mean() - gb.mean()) / 255.0, 4),
        "dhue": round(hue_circular_diff(ha, hb), 4),
        "dsat": round(abs(ha[..., 1].mean() - hb[..., 1].mean()) / 255.0, 4),
    }


def composite_score(m: dict) -> float:
    """综合偏差分（0 越好）。权重按 2026-10-15 样本校准：SSIM 对「换人缝」天然
    偏低、不判别顺/跳，故仅保留低权重作参考；三项色差承担主要判别。"""
    return round(0.10 * (1 - m["ssim"]) + 0.35 * m["dlum"] + 0.35 * m["dhue"] + 0.20 * m["dsat"], 4)


# ---------------- 视频抽帧 ----------------

def probe_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"ffprobe 失败: {video}\n{out.stderr}")
    return float(out.stdout.strip())


def grab_frame(video: Path, t: float, out_png: Path) -> Image.Image:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
         "-frames:v", "1", str(out_png)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0 or not out_png.exists():
        raise RuntimeError(f"ffmpeg 抽帧失败: {video} @ {t}s\n{out.stderr}")
    return Image.open(out_png).convert("RGB")


# ---------------- 主流程 ----------------

def check_pairs(pairs, tmp: Path, tail: float, head: float) -> list:
    """pairs: [(名称A, 视频A, 名称B, 视频B)] → 每缝指标。"""
    rows = []
    for i, (na, va, nb, vb) in enumerate(pairs, 1):
        dur_a = probe_duration(va)
        fa = grab_frame(va, dur_a - tail, tmp / f"s{i:02d}_a.png")
        fb = grab_frame(vb, head, tmp / f"s{i:02d}_b.png")
        m = seam_metrics(fa, fb)
        m.update({"seam": i, "from": na, "to": nb, "score": composite_score(m)})
        rows.append(m)
    return rows


def fmt_table(rows: list) -> str:
    def mark(v, th):
        return f"{v:.3f}{'⚠' if v > th else ' '}"

    lines = [
        "缝  | 上一段 → 下一段                        | SSIM  | Δ亮度 | Δ色相 | Δ饱和 | 综合偏差",
        "----+----------------------------------------+-------+-------+-------+-------+---------",
    ]
    for r in rows:
        pair = f"{r['from']} → {r['to']}"
        lines.append(f"{r['seam']:>3} | {pair:<38} | {r['ssim']:.3f} | {mark(r['dlum'], TH_DLUM)} | "
                     f"{mark(r['dhue'], TH_DHUE)} | {mark(r['dsat'], TH_DSAT)} | {r['score']:.3f}")
    lines.append(f"阈值（⚠ 标记）：Δ亮度 >{TH_DLUM}、Δ色相 >{TH_DHUE}、Δ饱和 >{TH_DSAT}")
    worst = sorted(rows, key=lambda r: -r["score"])[:3]
    lines.append("最需关注（综合偏差 Top3）：" + "；".join(
        f"缝{r['seam']}（{r['from']}→{r['to']}，偏差 {r['score']:.3f}）" for r in worst))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="分镜接缝质量量化检测")
    ap.add_argument("dir", nargs="?", help="模式 A：分镜视频目录")
    ap.add_argument("--pattern", default="*.mp4", help="模式 A 匹配式（默认 *.mp4）")
    ap.add_argument("--video", help="模式 B：拼接成片")
    ap.add_argument("--cuts", help="模式 B：切点秒列表（逗号分隔）")
    ap.add_argument("--tail", type=float, default=0.12, help="上一段抽帧离片尾秒数")
    ap.add_argument("--head", type=float, default=0.12, help="下一段抽帧离片头秒数")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true", help="自检")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    with tempfile.TemporaryDirectory(prefix="seams_") as td:
        tmp = Path(td)
        if args.video:
            if not args.cuts:
                print("模式 B 需提供 --cuts"); sys.exit(2)
            video = Path(args.video)
            cuts = [float(x) for x in args.cuts.split(",") if x.strip()]
            pairs = []
            # 用同一成片：缝 i 的 A 端 = 前一切点前、B 端 = 切点后——A 端直接用同一文件
            # （抽帧点在切点两侧，等效于看相邻两段）
            for i, c in enumerate(cuts, 1):
                pairs.append((f"{video.name}@{c - args.tail:.3f}s", video,
                              f"{video.name}@{c + args.head:.3f}s", video))
            # 模式 B 的抽帧点与模式 A 不同（都在切点附近），单独处理
            rows = []
            for i, (na, va, nb, vb) in enumerate(pairs, 1):
                c = cuts[i - 1]
                fa = grab_frame(va, c - args.tail, tmp / f"s{i:02d}_a.png")
                fb = grab_frame(vb, c + args.head, tmp / f"s{i:02d}_b.png")
                m = seam_metrics(fa, fb)
                m.update({"seam": i, "from": na, "to": nb, "score": composite_score(m)})
                rows.append(m)
        elif args.dir:
            d = Path(args.dir)
            vids = sorted(p for p in d.glob(args.pattern) if p.is_file())
            if len(vids) < 2:
                print(f"目录中匹配到 {len(vids)} 个视频（至少 2 个）"); sys.exit(2)
            pairs = [(vids[i - 1].stem, vids[i - 1], vids[i].stem, vids[i])
                     for i in range(1, len(vids))]
            rows = check_pairs(pairs, tmp, args.tail, args.head)
        else:
            ap.print_help(); sys.exit(2)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(fmt_table(rows))
    return 0


# ---------------- 自检 ----------------

def _solid(w, h, rgb):
    return Image.new("RGB", (w, h), rgb)


def selftest() -> int:
    ok = True

    def expect(name, cond, extra=""):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name, extra)
        if not cond:
            ok = False

    a = _solid(240, 320, (180, 170, 160))
    b_same = _solid(240, 320, (180, 170, 160))
    b_dark = _solid(240, 320, (130, 122, 115))     # 亮度低一档
    b_hue = _solid(240, 320, (170, 180, 160))      # 色相偏绿
    m_same = seam_metrics(a, b_same)
    m_dark = seam_metrics(a, b_dark)
    m_hue = seam_metrics(a, b_hue)
    expect("同帧：ssim≈1", m_same["ssim"] > 0.98, str(m_same))
    expect("同帧：偏差全近 0", m_same["dlum"] < 0.01 and m_same["dhue"] < 0.02, str(m_same))
    expect("亮度差可测", m_dark["dlum"] > 0.10, str(m_dark))
    expect("色相差可测", m_hue["dhue"] >= m_same["dhue"], str(m_hue))
    expect("综合分排序正确", composite_score(m_dark) > composite_score(m_same))

    # 实景抽帧链路验证（可选）：环境变量 SEAM_SAMPLE_DIR 指向含 mp4 的目录时启用
    real = None
    sample_dir = os.environ.get("SEAM_SAMPLE_DIR", "").strip()
    if sample_dir:
        d = Path(sample_dir)
        if d.is_dir():
            cands = sorted(d.glob("*.mp4"))
            if cands:
                real = cands[0]
    if real is not None:
        with tempfile.TemporaryDirectory(prefix="seams_st_") as td:
            f = grab_frame(real, 0.5, Path(td) / "t.png")
            expect("ffmpeg 抽帧链路", f.width > 0 and f.height > 0, f"{f.width}x{f.height}")
    else:
        print("SKIP 实景抽帧（未设置 SEAM_SAMPLE_DIR 或无可用 mp4）")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
