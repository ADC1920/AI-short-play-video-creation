#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宫格分镜 JSON 机检（ai-short-play-video 技能）。

校验宫格分镜智能体产出的 JSON 是否满足约束：
  C1 可解析的 JSON（容忍 ```json 围栏包裹；UTF-8/GBK 自动识别）
  C2 shots 数量与宫格数一致（2x2=4 / 2x3=6 / 3x3=9 / 5x5=25，可用 --n 覆盖）
  C3 每条 prompt_text 词数在 20-30（英文适用；中文提示词自动跳过）
  C4 字符数上限检查（--max-chars，默认 1500，超限计警告）
  C5 必含排除词（中英任一命中即过）：时间码/字幕
  C6 禁用句式（"A scene showing" / "There is a" / "in corner"）
  C7 shot_number 重复检测（重复计错误）

用法:
    python validate_storyboard.py <story.json> [--n 25|9|6|4] [--max-chars 1500]
    python validate_storyboard.py --selftest
退出码: 0=无错误, 1=存在错误, 2=用法/文件错误
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

FORBIDDEN = ["A scene showing", "There is a", "in corner"]
# 排除词组：组内任一命中即通过（中英兼容）
REQUIRED_GROUPS = [
    ("时间码排除词", ("no timecode", "无时间码", "不出现时间码", "无时间戳")),
    ("字幕排除词", ("no subtitles", "无字幕", "不出现字幕")),
]
WORD_RANGE = (20, 30)
DEFAULT_MAX_CHARS = 1500
CJK_SKIP_RATIO = 0.3  # 中文占比超过此值视为中文提示词，跳过英文词数检查
LAYOUT_N = {"5x5": 25, "3x3": 9, "2x2": 4, "2x3": 6, "3x2": 6}


def strip_fences(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    return m.group(1) if m else text


def read_text_any(path):
    """读取文本，UTF-8 优先，失败回退 GB18030（兼容 GBK 编码的中文 JSON）。"""
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法按 UTF-8/GB18030 解码该文件")


def load(path):
    """读取分镜 JSON 文件（容忍 ```json 围栏包裹）。"""
    return json.loads(strip_fences(read_text_any(path)))


def cjk_ratio(s):
    if not s:
        return 0.0
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(s)


def check(data, expect_n, max_chars=DEFAULT_MAX_CHARS):
    errors, warnings = [], []
    layout = str(data.get("grid_layout", ""))
    shots = data.get("shots")
    if not isinstance(shots, list):
        errors.append("缺少 shots 数组")
        return errors, warnings

    n = expect_n or LAYOUT_N.get(layout)
    if n is None:
        warnings.append(f"grid_layout={layout!r} 无法推断数量，跳过数量检查")
    elif len(shots) != n:
        errors.append(f"shots 数量 {len(shots)} != 应为 {n}（grid_layout={layout or '未填'}）")

    seen_numbers = {}
    cjk_skip_noted = False
    for i, shot in enumerate(shots, 1):
        tag = f"分镜{i}"
        if not isinstance(shot, dict):
            errors.append(f"{tag}: 不是对象")
            continue
        prompt = shot.get("prompt_text", "")
        num = shot.get("shot_number")
        if not num:
            warnings.append(f"{tag}: 缺 shot_number")
        else:
            if num in seen_numbers:
                errors.append(f"{tag}: shot_number {num!r} 与 {seen_numbers[num]} 重复")
            else:
                seen_numbers[num] = tag
        if len(prompt) > max_chars:
            warnings.append(f"{tag}: 字符数 {len(prompt)} 超上限 {max_chars}（实测超 1600 失败率显著上升，建议拆镜或精简）")
        if cjk_ratio(prompt) >= CJK_SKIP_RATIO:
            if not cjk_skip_noted:
                warnings.append("检测到中文提示词，词数检查（20-30 英文词）不适用，已跳过")
                cjk_skip_noted = True
        else:
            words = len(prompt.split())
            if not WORD_RANGE[0] <= words <= WORD_RANGE[1]:
                warnings.append(f"{tag}: 词数 {words} 超出 {WORD_RANGE[0]}-{WORD_RANGE[1]}")
        for label, options in REQUIRED_GROUPS:
            if not any(o in prompt for o in options):
                errors.append(f"{tag}: 缺{label}（应含 {' 或 '.join(options[:2])}）")
        for bad in FORBIDDEN:
            if bad.lower() in prompt.lower():
                errors.append(f"{tag}: 含禁用句式 {bad!r}")
    return errors, warnings


def selftest():
    good_prompt = ("Medium Shot, the woman from image_1.png grips her sword tightly, "
                   "intense expression, snow background, cinematic lighting, "
                   "no timecode, no subtitles.")
    cn_prompt = ("中景，雪地中持剑女子紧握长剑，神情凛冽，电影级打光，"
                 "无时间码，无字幕。")
    bad_prompt = ("A scene showing a village in the mountains at dawn, "
                  "beautiful warm light over the rooftops, highly detailed.")
    good = {"grid_layout": "3x3", "grid_aspect_ratio": "16:9",
            "shots": [{"shot_number": str(i), "prompt_text": good_prompt} for i in range(1, 10)]}
    cn = {"grid_layout": "3x3",
          "shots": [{"shot_number": str(i), "prompt_text": cn_prompt} for i in range(1, 10)]}
    bad = {"grid_layout": "3x3",
           "shots": [{"shot_number": "1", "prompt_text": bad_prompt}] * 8}
    dup = {"grid_layout": "2x2",
           "shots": [{"shot_number": "1", "prompt_text": good_prompt} for _ in range(4)]}
    e1, _ = check(good, None)
    e2, _ = check(bad, None)
    e3, w3 = check(cn, None)
    e4, _ = check(dup, None)
    assert not e1, f"英文正例误报: {e1}"
    assert not e3, f"中文正例误报: {e3}"
    assert not any("分镜" in w and "超出" in w for w in w3), f"中文词数检查未跳过: {w3}"
    assert len(e2) >= 3, f"负例漏报: {e2}"  # 数量 8!=9 + 禁用句式 + 2 组必含词缺失
    assert any("重复" in e for e in e4), f"编号重复未检出: {e4}"
    # 字符上限：超长 prompt 应出现警告
    long_shot = {"grid_layout": "2x2", "shots": [
        {"shot_number": str(i), "prompt_text": good_prompt + " detail" * 250} for i in range(1, 5)]}
    _, w5 = check(long_shot, None)
    assert any("字符数" in w for w in w5), f"超长未警告: {w5[:3]}"
    # 文件读取路径回归（含围栏与编码回退路径）
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "sb.json"
        f.write_text("```json\n" + json.dumps(good) + "\n```", encoding="utf-8")
        e6, _ = check(load(f), None)
        assert not e6, f"文件读取路径误报: {e6}"
    print("selftest PASS（英文正例 0 错；中文正例 0 错且词数跳过；负例抓到 %d 错；编号重复检出；超长告警；文件读取通过）" % len(e2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="分镜 JSON 文件（容忍 ```json 围栏）")
    ap.add_argument("--n", type=int, choices=(4, 6, 9, 25), help="期望 shots 数量，默认按 grid_layout 推断")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help=f"单条提示词字符上限，默认 {DEFAULT_MAX_CHARS}")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.file:
        ap.print_help()
        return 2
    try:
        data = load(args.file)
    except FileNotFoundError:
        print(f"文件不存在: {args.file}")
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"C1 JSON 解析失败: {exc}")
        return 1

    errors, warnings = check(data, args.n, args.max_chars)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}")
    print("PASS" if not errors else f"FAIL（{len(errors)} 错误 / {len(warnings)} 警告）")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
