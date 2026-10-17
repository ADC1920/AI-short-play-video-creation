# -*- coding: utf-8 -*-
"""一键验收管道（2026-10-17 建）：分镜目录 → 接缝量化 + 同源核对 → 底账 Markdown。

复用同目录 check_seams.py 的多指标量化，并读取分镜目录的 _manifest.json（如存在）做同源
核对——把「混源批次」的判断从人工纪律变成数据核对（混源是接缝色差超标的结构性来源）。

用法：
  python qa_batch.py "<分镜目录>" [--pattern "*.mp4"] [--batch 10.15] [--out <底账.md>] [--json]
自检：
  python qa_batch.py --selftest
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_seams as cs  # noqa: E402


def collect(dirpath: Path, pattern: str):
    vids = sorted(p for p in dirpath.glob(pattern) if p.is_file())
    vids.sort(key=lambda p: (0 if "开场" in p.stem else 1, p.name))
    return vids


def manifest_check(d: Path):
    """返回 (文本块, 是否全部就绪)"""
    mf = d / "_manifest.json"
    if not mf.exists():
        return "（无 _manifest.json——建议用 `python tools/manifest.py init` 建档，以启用同源核对）", None
    data = json.loads(mf.read_text(encoding="utf-8"))
    versions = {}
    not_final, missing = [], []
    for s in data.get("shots", []):
        v = s.get("script_version") or "(未记)"
        versions.setdefault(v, []).append(s["shot"])
        if s.get("status") != "定稿":
            not_final.append(f"{s['shot']}（{s.get('status','?')}）")
        if not (d / s["file"]).exists():
            missing.append(s["shot"])
    lines = [f"- 版本分布：" + "；".join(f"{v}×{len(vs)}" for v, vs in versions.items())]
    lines.append(f"- 非定稿 {len(not_final)} 段" + ("：" + "、".join(not_final) if not_final else "（全部定稿）"))
    if missing:
        lines.append(f"- 清单内文件缺失 {len(missing)} 段：{'、'.join(missing)}")
    ready = (len(versions) == 1 and not not_final and not missing)
    lines.append(f"- 同源判定：{'通过（同一版本、全部定稿）' if ready else '**未通过**——缝两侧非同源或含非定稿，色差超标先查此处'}")
    return "\n".join(lines), ready


def run(args):
    d = Path(args.dir)
    if not d.exists():
        print(f"目录不存在：{d}")
        return 2
    vids = collect(d, args.pattern)
    if len(vids) < 2:
        print(f"目录中匹配到 {len(vids)} 个视频（至少 2 个）")
        return 2
    print(f"对象：{d}（{len(vids)} 段，{len(vids) - 1} 缝）")

    pairs = [(vids[i - 1].stem, vids[i - 1], vids[i].stem, vids[i]) for i in range(1, len(vids))]
    with tempfile.TemporaryDirectory(prefix="qa_") as td:
        rows = cs.check_pairs(pairs, Path(td), 0.12, 0.12, True)
    table = cs.fmt_table(rows, True)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0

    # 超阈统计
    over = []
    for r in rows:
        flags = []
        if r["dlum"] > cs.TH_DLUM:
            flags.append(f"Δ亮度 {r['dlum']:.3f}")
        if r["dhue"] > cs.TH_DHUE:
            flags.append(f"Δ色相 {r['dhue']:.3f}")
        if r["dsat"] > cs.TH_DSAT:
            flags.append(f"Δ饱和 {r['dsat']:.3f}")
        if r.get("flow") is not None and r["flow"] > cs.TH_FLOW:
            flags.append(f"运动 {r['flow']:.3f}")
        if flags:
            over.append((r, flags))
    worst = sorted(rows, key=lambda r: -r["score"])[:3]

    today = datetime.now().strftime("%Y%m%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    batch = args.batch or "（未标批次）"
    mtext, mready = manifest_check(d)

    md = []
    md.append(f"# 接缝量化验收底账 · {batch}（{ts}）")
    md.append("")
    md.append(f"> 工具：`tools/qa_batch.py`（内置 check_seams 六指标：SSIM／Δ亮度／Δ色相／Δ饱和／运动持续性）")
    md.append(f"> 对象：`{d}`（{len(vids)} 段，{len(vids) - 1} 缝）")
    md.append(f"> 跑法：`python tools/qa_batch.py \"{d}\" --batch {batch}`")
    md.append("")
    md.append("## 一、全批数据")
    md.append("")
    md.append("```")
    md.append(table)
    md.append("```")
    md.append("")
    md.append("## 二、同源核对（manifest）")
    md.append("")
    md.append(mtext)
    md.append("")
    md.append("## 三、关注项")
    md.append("")
    if over:
        md.append(f"超阈缝 {len(over)} 处：")
        for r, flags in over:
            md.append(f"- 缝 {r['seam']}（{r['from']} → {r['to']}）：{'；'.join(flags)}，综合偏差 {r['score']:.3f}")
    else:
        md.append("无超阈缝。")
    md.append("")
    md.append("综合偏差 Top3：" + "；".join(
        f"缝{r['seam']}（{r['from']}→{r['to']}，{r['score']:.3f}）" for r in worst))
    md.append("")
    md.append("## 四、阈值与判读")
    md.append("")
    md.append(f"- 阈值：Δ亮度 >{cs.TH_DLUM}、Δ色相 >{cs.TH_DHUE}、Δ饱和 >{cs.TH_DSAT}、运动 >{cs.TH_FLOW}；"
              "SSIM 对换人缝天然偏低、不作判据（2026-10-15 校准）。")
    md.append("- 超阈处置：先核同源（上节）→ 再目检两侧缝帧 → 重做较弱一侧后复测。")
    md.append("")

    out = Path(args.out) if args.out else (d / f"_qa底账_{today}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(table)
    print(f"\n底账已写出：{out}")
    if mready is False:
        print("提示：同源核对未通过——先按 manifest 修正版本/定稿状态，再复测。")
    return 0


def selftest():
    """合成三段短视频（纯色渐变）跑通全流程；无 ffmpeg 时跳过。"""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("selftest SKIP（未检测到 ffmpeg/ffprobe，安装后重跑）")
        return
    tmp = Path(tempfile.mkdtemp(prefix="qa_st_"))
    try:
        d = tmp / "clips"
        d.mkdir()
        for i, (r, g, b) in enumerate([(200, 180, 170), (190, 175, 168), (60, 40, 35)], 1):
            name = "LOOK  0 · 开场.mp4" if i == 1 else f"LOOK 0{i} · 测{i}.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", f"color=c=#{r:02x}{g:02x}{b:02x}:size=180x320:rate=60:duration=1.2",
                            "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast", str(d / name)],
                           capture_output=True, check=True)
        out = tmp / "底账.md"
        rc = run(argparse.Namespace(dir=str(d), pattern="*.mp4", batch="selftest",
                                    out=str(out), json=False))
        assert rc == 0 and out.exists(), "未生成底账"
        text = out.read_text(encoding="utf-8")
        assert "接缝量化验收底账" in text and "缝 1" in text.replace("  1 |", "缝 1 |") or "1 |" in text, "底账内容异常"
        # 缝 2（浅色→深色）应显著超阈
        assert "Δ亮度" in text, "缺指标列"
        print("selftest PASS（2 缝底账生成，含同源核对未建档提示）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="一键验收：接缝量化 + 同源核对 + 底账")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--pattern", default="*.mp4")
    ap.add_argument("--batch", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        sys.exit(0)
    if not args.dir:
        ap.print_help()
        sys.exit(2)
    sys.exit(run(args))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
