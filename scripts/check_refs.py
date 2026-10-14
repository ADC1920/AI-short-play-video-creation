#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材与 @ 引用核对（ai-short-play-video-creation 技能）。

核对「@ 引用名」与素材目录文件名是否一致（技能铁律：@名称必须与素材名完全一致）。
双向报告：
  - 断链引用（错误）：文本里的 @X 在素材目录找不到对应文件
  - 待补引用（警告）：断链、但该行已标注「待补」——素材未就绪的显式缺口，不算错误
  - 闲置素材（警告）：素材目录里的文件未被任何文本引用
  - 大小写不一致（警告）：仅大小写不同，可能因平台差异导致引用失效

`--bindings`（可选）：多素材绑定自检——段落内 ≥3 个 @引用且没有任何绑定说明
（「只使用 / 只参考 / 不得……」类）时告警：多素材未写「谁控什么、不从中取什么」
易互相污染（纪律见 `references/prompt-craft.md` 多素材绑定节）。

默认输入 = 项目目录（自动找 素材/ 子目录与全部文本文件）；
也可手动指定 --assets / --texts。

用法:
    python check_refs.py <项目目录> [--bindings]
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
# 待补标注词：断链引用所在行含此词时归为「待补清单」（警告级）而非断链错误
PENDING_MARK = "待补"
# 绑定说明词表（--bindings 检查用）：出现任一即视为已写绑定
BINDING_WORDS = ("只使用", "只参考", "只取", "只用", "仅用", "仅取", "只提供", "仅提供",
                 "不要用", "不得", "不继承", "用途", "控制范围", "只控", "只用来")


def is_ignored(name):
    return name in IGNORE_NAMES or IGNORE_RE.match(name) or len(name) > MAX_REF_LEN


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
    """扫描文本文件，返回 (refs, line_texts, contents)。

    refs: 引用名 -> {文件: [行号,...]}；line_texts: {(文件, 行号): 行文本}；contents: {文件: 全文}。
    """
    refs = {}
    line_texts = {}
    contents = {}
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
        contents[str(f)] = content
        for lineno, line in enumerate(content.splitlines(), 1):
            line_texts[(str(f), lineno)] = line
            for m in REF_RE.finditer(line):
                name = m.group(1)
                if is_ignored(name):
                    continue
                refs.setdefault(name, {}).setdefault(str(f), []).append(lineno)
    return refs, line_texts, contents


def check(assets, refs, line_texts=None):
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
            # 区分「显式待补」与「意外断链」：待补行降级为警告
            pending_locs, broken_locs = [], []
            for f, linenos in refs[name].items():
                for ln in linenos:
                    line = (line_texts or {}).get((f, ln), "")
                    (pending_locs if PENDING_MARK in line else broken_locs).append((f, ln))
            if broken_locs:
                where = "、".join(f"{f}:{l}" for f, l in broken_locs[:3])
                errors.append(f"断链引用 @{name}（{where}）——素材目录无对应文件")
            if pending_locs:
                where = "、".join(f"{f}:{l}" for f, l in pending_locs[:3])
                warnings.append(f"待补引用 @{name}（{where} 已标注待补）——素材未就绪，出图后复跑本核对")
    used = {n for n in refs if n in assets}
    for name in sorted(assets):
        if name not in used:
            warnings.append(f"闲置素材 {name!r}（{assets[name].name}）未被任何文本引用")
    return errors, warnings


def iter_paragraphs(content):
    """按空行切分段落，返回 (起始行号, 段落文本)。"""
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            yield start, "\n".join(lines[start - 1:i - 1])
            start = None
    if start is not None:
        yield start, "\n".join(lines[start - 1:])


def check_bindings(content, file_label):
    """多素材绑定自检：段落内 ≥3 个 @引用（不计表格/代码行）且无绑定说明 → 告警。"""
    warns = []
    for start, para in iter_paragraphs(content):
        body = "\n".join(l for l in para.splitlines()
                         if not l.lstrip().startswith(("|", "```", "-", "*")))
        names = [m.group(1) for m in REF_RE.finditer(body) if not is_ignored(m.group(1))]
        names = list(dict.fromkeys(names))
        if len(names) >= 3 and not any(bw in para for bw in BINDING_WORDS):
            warns.append(f"多素材段落未写绑定说明（{file_label}:{start}，@引用 {len(names)} 个：{'、'.join(names)}）"
                         f"——建议逐个写明「只使用什么 / 不从中取什么」（见 prompt-craft 多素材绑定节）")
    return warns


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
            "开场 @顾寒 走入 @破败茶棚 遇袭。\n参考 @图片1 构图；@角色名 占位示例。\n"
            "@缺图角色 先入镜（待补）。\n",
            encoding="utf-8")
        sb = ep / "分镜"
        sb.mkdir()
        (sb / "sb.json").write_text(
            '{"shots": [{"prompt_text": "@顾寒 @奈奈 对峙"}]}', encoding="utf-8")
        assets_map = collect_assets(assets)
        refs, line_texts, contents = collect_refs([root])
        errs, warns = check(assets_map, refs, line_texts)
        assert any("奈奈" in e for e in errs), f"断链引用未检出: {errs}"
        assert not any("顾寒" in e for e in errs), f"正常引用误报: {errs}"
        assert not any("图片" in e or "角色名" in e for e in errs), f"占位词未忽略: {errs}"
        assert any("刀疤" in w for w in warns), f"闲置素材未检出: {warns}"
        # 待补标注：断链但标注待补 → 警告级而非错误
        assert not any("缺图角色" in e for e in errs), f"待补引用误报为断链: {errs}"
        assert any("待补引用 @缺图角色" in w for w in warns), f"待补引用未入清单: {warns}"
        # 空素材目录路径
        empty = root / "空素材"
        empty.mkdir()
        errs2, _ = check(collect_assets(empty), refs, line_texts)
        assert any("为空或不存在" in e for e in errs2), f"空素材目录未报告: {errs2}"
        # 大小写警告路径
        errs3, warns3 = check({"GUHAN": assets_map["顾寒"]}, {"guhan": {}}, {})
        assert any("大小写" in w for w in warns3), f"大小写警告未检出: {warns3}"
        # 绑定自检：≥3 引用且无绑定说明 → 告警；有绑定词或表格行 → 不报警
        no_bind = "第2集/提示词.md"
        w1 = check_bindings("@顾寒 @奈奈 @刀疤 在茶棚对峙，剑光四起。", no_bind)
        assert any("多素材段落未写绑定说明" in w for w in w1), f"绑定缺失未检出: {w1}"
        w2 = check_bindings(
            "角色A 对应 @顾寒：只使用外形，不用背景。\n场景参考 @破败茶棚：只取布局。\n道具 @刀疤 不要用图中的人。", no_bind)
        assert not w2, f"有绑定说明误报: {w2}"
        w3 = check_bindings("| 角色A | @顾寒 | 顾寒.png |\n| 角色B | @奈奈 | 奈奈.png |\n| 场景 | @刀疤 | 刀疤.png |", no_bind)
        assert not w3, f"表格行误报: {w3}"
        assert contents, "contents 为空"
    print("selftest PASS（断链检出 / 正常引用不误报 / 占位词忽略 / 闲置检出 / 空目录路径 / 大小写路径 / "
          "待补标注降级 / 绑定自检三路径）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?", help="项目目录（自动找 素材/ 与全部文本）")
    ap.add_argument("--assets", help="素材目录（默认 <项目>/素材）")
    ap.add_argument("--texts", action="append", default=[], help="文本文件或目录（可多次；默认整个项目目录）")
    ap.add_argument("--bindings", action="store_true", help="多素材绑定自检（默认关）")
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
    refs, line_texts, contents = collect_refs(texts)
    print(f"素材 {len(assets)} 件 | 引用名 {len(refs)} 个")
    errors, warnings = check(assets, refs, line_texts)
    if args.bindings:
        for fname, content in contents.items():
            warnings += check_bindings(content, fname)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}")
    print("PASS（无断链）" if not errors else f"FAIL（{len(errors)} 断链 / {len(warnings)} 警告）")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
