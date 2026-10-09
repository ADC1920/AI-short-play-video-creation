#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材与 @ 引用核对（ai-short-play-video 技能）。

核对「@ 引用名」与素材目录文件名是否一致（技能铁律：@名称必须与素材名完全一致）。
双向报告：
  - 断链引用（错误）：文本里的 @X 在素材目录找不到对应文件
  - 闲置素材（警告）：素材目录里的文件未被任何文本引用
  - 大小写不一致（警告）：仅大小写不同，可能因平台差异导致引用失效

默认输入 = 项目目录（自动找 素材/ 子目录与全部文本文件）；
也可手动指定 --assets / --texts。

用法:
    python check_refs.py <项目目录>
    python check_refs.py --assets <素材目录> --texts <目录或文件> [--texts ...]
    python check_refs.py --selftest
退出码: 0=无断链, 1=存在断链引用, 2=用法/路径错误
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

TEXT_EXTS = {".md", ".txt", ".json"}
ASSET_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
REF_RE = re.compile(r"@([A-Za-z0-9_\-\u4e00-\u9fff]+)")
# 通用占位/平台语法，不是素材引用
IGNORE_NAMES = {"角色名", "场景名", "素材名", "对应素材", "角色", "场景", "道具"}
IGNORE_RE = re.compile(r"^(图片|视频|音频)\d*$")
# 技能文档自身的元引用（出现在说明性文字里），实际项目文件一般不会用
MAX_REF_LEN = 40


def collect_assets(assets_dir):
    """素材名 -> 文件路径（stem 即素材注册名）。"""
    d = Path(assets_dir)
    if not d.is_dir():
        return None
    out = {}
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in ASSET_EXTS:
            out.setdefault(f.stem, f)
    return out


def collect_refs(texts):
    """扫描文本文件，返回 引用名 -> {文件: [行号,...]}。"""
    refs = {}
    files = []
    for t in texts:
        p = Path(t)
        if p.is_dir():
            files += [c for c in sorted(p.rglob("*")) if c.is_file() and c.suffix.lower() in TEXT_EXTS]
        elif p.is_file():
            files.append(p)
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = f.read_text(encoding="gb18030")
        for lineno, line in enumerate(content.splitlines(), 1):
            for m in REF_RE.finditer(line):
                name = m.group(1)
                if name in IGNORE_NAMES or IGNORE_RE.match(name) or len(name) > MAX_REF_LEN:
                    continue
                refs.setdefault(name, {}).setdefault(str(f), []).append(lineno)
    return refs


def check(assets, refs):
    errors, warnings = [], []
    fold_map = {k.casefold(): k for k in assets}
    if not assets:
        errors.append("素材目录为空或不存在——所有引用均视为断链（请先做素材）")
    else:
        for name in sorted(refs):
            if name in assets:
                continue
            if name.casefold() in fold_map:
                warnings.append(f"引用 @{name} 与素材 {fold_map[name.casefold()]!r} 仅大小写不同，平台侧可能引用失效")
                continue
            locs = refs[name]
            where = "、".join(f"{f}:{l[0]}" for f, l in list(locs.items())[:3])
            errors.append(f"断链引用 @{name}（{where}）——素材目录无对应文件")
    used = {n for n in refs if n in assets}
    for name in sorted(assets):
        if name not in used:
            warnings.append(f"闲置素材 {name!r}（{assets[name].name}）未被任何文本引用")
    return errors, warnings


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assets = root / "素材"
        assets.mkdir()
        for n in ["顾寒", "破败茶棚", "刀疤"]:
            (assets / f"{n}.png").write_bytes(b"x")
        ep = root / "第1集"
        ep.mkdir()
        (ep / "剧本.md").write_text(
            "开场 @顾寒 走入 @破败茶棚 遇袭。\n参考 @图片1 构图；@角色名 占位示例。\n",
            encoding="utf-8")
        sb = ep / "分镜"
        sb.mkdir()
        (sb / "sb.json").write_text(
            '{"shots": [{"prompt_text": "@顾寒 @奈奈 对峙"}]}', encoding="utf-8")
        assets_map = collect_assets(assets)
        refs = collect_refs([root])
        errs, warns = check(assets_map, refs)
        assert any("奈奈" in e for e in errs), f"断链引用未检出: {errs}"
        assert not any("顾寒" in e for e in errs), f"正常引用误报: {errs}"
        assert not any("图片" in e or "角色名" in e for e in errs), f"占位词未忽略: {errs}"
        assert any("刀疤" in w for w in warns), f"闲置素材未检出: {warns}"
        # 空素材目录路径
        empty = root / "空素材"
        empty.mkdir()
        errs2, _ = check(collect_assets(empty), refs)
        assert any("为空或不存在" in e for e in errs2), f"空素材目录未报告: {errs2}"
        # 大小写警告路径
        errs3, warns3 = check({"GUHAN": assets_map["顾寒"]}, {"guhan": {}})
        assert any("大小写" in w for w in warns3), f"大小写警告未检出: {warns3}"
    print("selftest PASS（断链检出 / 正常引用不误报 / 占位词忽略 / 闲置检出 / 空目录路径 / 大小写路径）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?", help="项目目录（自动找 素材/ 与全部文本）")
    ap.add_argument("--assets", help="素材目录（默认 <项目>/素材）")
    ap.add_argument("--texts", action="append", default=[], help="文本文件或目录（可多次；默认整个项目目录）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.assets:
        assets_dir = Path(args.assets)
    elif args.project:
        assets_dir = Path(args.project) / "素材"
        if not assets_dir.is_dir():
            assets_dir = Path(args.project)
    else:
        ap.print_help()
        return 2

    texts = [Path(t) for t in args.texts] if args.texts else ([Path(args.project)] if args.project else None)
    if not texts:
        ap.print_help()
        return 2
    for p in [assets_dir] + texts:
        if not p.exists():
            print(f"路径不存在: {p}")
            return 2

    assets = collect_assets(assets_dir)
    if assets is None:
        print(f"素材目录不存在: {assets_dir}")
        return 2
    refs = collect_refs(texts)
    print(f"素材 {len(assets)} 件 | 引用名 {len(refs)} 个")
    errors, warnings = check(assets, refs)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}")
    print("PASS（无断链）" if not errors else f"FAIL（{len(errors)} 断链 / {len(warnings)} 警告）")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
