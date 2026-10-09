#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地宫格拼图（ai-short-play-video-creation 技能）。把多张图按序拼成宫格，替代在线拼图工具。

默认 9 张拼 3×3 九宫格（场景九宫格工作流）；--cols 5 支持 25 张拼 5×5。
图片顺序按文件名中的数字自然排序（1.png、2.png…或含数字的任意命名）。

依赖: pip install pillow
用法:
    python make_grid.py -o grid.png 图1.png 图2.png ... 图9.png
    python make_grid.py -o grid.png <图片目录> [--cols 5] [--tile 1024]
    python make_grid.py --selftest
退出码: 0=成功, 2=用法/输入错误
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("缺少依赖: pip install pillow")
    sys.exit(2)

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
CELL_COLORS = [(255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 255, 0), (128, 0, 128),
               (0, 255, 255), (255, 165, 0), (0, 0, 0), (255, 255, 255)]


def natural_key(p):
    nums = re.findall(r"\d+", p.stem)
    return (int(nums[-1]) if nums else 10**9, p.name)


def collect(paths):
    files = []
    for p in paths:
        f = Path(p)
        if f.is_dir():
            files += [c for c in sorted(f.iterdir()) if c.suffix.lower() in EXTS]
        elif f.suffix.lower() in EXTS:
            files.append(f)
        else:
            print(f"跳过非图片: {f}")
    return sorted(files, key=natural_key)


def make_grid(files, out, cols, tile):
    n = len(files)
    if n == 0:
        print("没有可用图片")
        return 2
    rows = -(-n // cols)  # ceil
    grid = Image.new("RGB", (cols * tile, rows * tile), (255, 255, 255))
    for i, f in enumerate(files):
        img = Image.open(f).convert("RGB")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2,
                        (w + side) // 2, (h + side) // 2)).resize((tile, tile))
        grid.paste(img, ((i % cols) * tile, (i // cols) * tile))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out)
    print(f"已生成 {out}（{cols}×{rows}，{n} 张图，单元格 {tile}px）")
    return 0


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, color in enumerate(CELL_COLORS, 1):
            f = Path(tmp) / f"{i}.png"
            Image.new("RGB", (64, 64), color).save(f)
            files.append(f)
        out = Path(tmp) / "grid.png"
        rc = make_grid(files, out, 3, 64)
        assert rc == 0
        grid = Image.open(out)
        assert grid.size == (192, 192), grid.size
        for i, color in enumerate(CELL_COLORS):
            px = grid.getpixel(((i % 3) * 64 + 32, (i // 3) * 64 + 32))
            assert px == color, (i, px, color)
        # 2×2 四宫格回归（2026-10-09：宫格数选择面扩展后纳入自检）
        files4 = []
        for i, color in enumerate(CELL_COLORS[:4]):
            f = Path(tmp) / f"q{i}.png"
            Image.new("RGB", (64, 64), color).save(f)
            files4.append(f)
        out4 = Path(tmp) / "grid2x2.png"
        rc4 = make_grid(files4, out4, 2, 64)
        assert rc4 == 0
        g4 = Image.open(out4)
        assert g4.size == (128, 128), g4.size
        for i, color in enumerate(CELL_COLORS[:4]):
            px = g4.getpixel(((i % 2) * 64 + 32, (i // 2) * 64 + 32))
            assert px == color, (i, px, color)
    print("selftest PASS（9 色块 3×3 + 4 色块 2×2，位置与颜色逐格核对）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="图片文件或目录（可混用）")
    ap.add_argument("-o", "--out", default="grid.png", help="输出文件，默认 grid.png")
    ap.add_argument("--cols", type=int, default=3, help="列数，默认 3（九宫格）；25 图用 5")
    ap.add_argument("--tile", type=int, default=1024, help="单元格边长 px，默认 1024")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.paths:
        ap.print_help()
        return 2
    return make_grid(collect(args.paths), args.out, args.cols, args.tile)


if __name__ == "__main__":
    sys.exit(main())
