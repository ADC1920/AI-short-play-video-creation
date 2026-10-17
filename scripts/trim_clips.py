# -*- coding: utf-8 -*-
"""分镜统一裁切工具（2026-10-17 建）。

按脚本 1.6 帧级规则：每段裁至 5.000 秒（300 帧＝10 拍），切点逐点落 120 BPM 重拍。
替代手工逐段裁切：默认重编码（帧精度优先，crf 17），--fast 走流复制（快但不精确）。
输出到 <分镜目录>/裁切_5s/（或 --out 指定）；源文件不动。

用法：
  python tools/trim_clips.py <分镜目录>                        # 干跑：列时长与计划
  python tools/trim_clips.py <分镜目录> --apply                # 执行裁切
  python tools/trim_clips.py <分镜目录> --duration 5.0 --pattern "LOOK*.mp4"
  python tools/trim_clips.py --selftest                        # 合成测试片自检
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def probe_duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return -1.0


def trim_one(src: Path, out: Path, duration: float, fast: bool):
    out.parent.mkdir(parents=True, exist_ok=True)
    if fast:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", f"{duration:.3f}",
               "-c", "copy", str(out)]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", f"{duration:.3f}",
               "-c:v", "libx264", "-crf", "17", "-preset", "fast", "-c:a", "copy", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr.strip()[-300:]
    return True, ""


def run(args):
    d = Path(args.dir)
    files = sorted([p for p in d.glob(args.pattern) if p.is_file()])
    if not files:
        print(f"目录内无匹配文件：{d} / {args.pattern}")
        sys.exit(2)
    outdir = Path(args.out) if args.out else (d / "裁切_5s")
    print(f"目录: {d}（{len(files)} 段）  目标时长: {args.duration:.3f}s  输出: {outdir}"
          f"  模式: {'流复制(快)' if args.fast else '重编码(帧精确)'}")
    print(f"{'文件':<28}{'原时长':>9}{'计划':>9}  说明")
    plan = []
    for f in files:
        dur = probe_duration(f)
        note = "" if dur > 0 else "时长读取失败"
        if 0 < dur <= args.duration + 0.001:
            note = note or f"已不足 {args.duration:.3f}s，跳过"
        plan.append((f, dur, note))
        print(f"{f.name:<28}{dur:>9.3f}{args.duration:>9.3f}  {note}")
    if not args.apply:
        print("\n干跑：加 --apply 执行裁切（源文件不动，输出到以上目录）")
        return 0
    okn = 0
    for f, dur, note in plan:
        if note.startswith("已不足") or dur <= 0:
            continue
        out = outdir / f.name
        ok, err = trim_one(f, out, args.duration, args.fast)
        if ok:
            real = probe_duration(out)
            flag = "✓" if real <= args.duration + 0.05 else "!!"
            print(f"{flag} {f.name} → {real:.3f}s")
            okn += 1
        else:
            print(f"!! {f.name} 失败: {err}")
    print(f"\n完成 {okn} 段，输出目录：{outdir}")
    return 0


def selftest():
    """合成 6 秒测试片裁到 5 秒验证帧精度；无 ffmpeg 时跳过。"""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("selftest SKIP（未检测到 ffmpeg/ffprobe，安装后重跑）")
        return
    tmp = Path(tempfile.mkdtemp(prefix="trim_st_"))
    try:
        src = tmp / "test6s.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", "testsrc=duration=6:size=180x320:rate=60",
                            "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast", str(src)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"生成测试片失败: {r.stderr[-200:]}"
        d0 = probe_duration(src)
        out = tmp / "out" / "test6s.mp4"
        ok, err = trim_one(src, out, 5.0, fast=False)
        assert ok, err
        d1 = probe_duration(out)
        assert 4.9 <= d1 <= 5.05, f"裁切时长偏差: {d1}"
        print(f"selftest PASS（6.000s → {d1:.3f}s，帧精确模式）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="分镜统一裁切（默认干跑）")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--pattern", default="*.mp4")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fast", action="store_true", help="流复制模式（快，切点不精确）")
    ap.add_argument("--apply", action="store_true", help="执行裁切（默认只干跑）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.dir:
        ap.print_help()
        sys.exit(2)
    sys.exit(run(args))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
