#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宫格分镜 JSON 机检（ai-short-play-video-creation 技能）。

校验宫格分镜智能体产出的 JSON 是否满足约束：
  C1 可解析的 JSON（容忍 ```json 围栏包裹；UTF-8/GBK 自动识别）
  C2 shots 数量与宫格数一致（2x2=4 / 2x3=6 / 3x3=9 / 5x5=25，可用 --n 覆盖）
  C3 每条 prompt_text 词数在 20-30（英文适用；中文提示词自动跳过）
  C4 字符数上限检查（--max-chars，默认 1500，超限计警告）
  C5 必含排除词（中英任一命中即过）：时间码/字幕
  C6 禁用句式（"A scene showing" / "There is a" / "in corner"）
  C7 shot_number 重复检测（重复计错误）
  C8 否定式高关联约束告警（光效/表情/空镜的「不 X / 无 X」写法，被禁词根会被当画面词渲染）
  C9 并列主体句式告警（「同框/一同入画」类写法易被渲染成两个主体）
  C10 抽象过程形态词告警（「成线/如注」类模型无法命名的过程形态）

C8/C9/C10 为告警级经验检查，来源见 `references/prompt-craft.md`「否定失效三改法」节
（实测词表，单例性质——命中不等于必错，按提示改写或忽略）。

门失败统计：每次校验默认把结果追加到目标文件同目录的 `.gate-log.jsonl`
（`--no-log` 关闭；`--stats` 汇总「哪道检查最常响」；`--log-file` 指定路径；写不进去静默跳过；
超过上限自动轮转，保留最近一半记录）。

用法:
    python validate_storyboard.py <story.json> [--n 25|9|6|4] [--max-chars 1500] [--no-log]
    python validate_storyboard.py <story.json> --stats
    python validate_storyboard.py --selftest
退出码: 0=无错误, 1=存在错误, 2=用法/文件错误
"""
import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
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
GATE_LOG_NAME = ".gate-log.jsonl"
GATE_LOG_MAX_LINES = 2000  # 门日志上限，超过时截去前一半（保留最近记录）

# C8：否定式高关联约束。视频模型对否定不敏感、对词根敏感——被禁词根留在提示词里会被当画面词渲染。
# 词表与判据来源：同业实测（manju-laoli-skill，单例性质），只覆盖「光效/表情/空镜」三类高关联概念；
# 低关联瑕疵（字幕/水印/变形）的否定式兜底不受此检查影响（仍属推荐写法）。
NEGATION_SAFE = ("不禁", "不由", "不自觉", "不知不觉", "不紧不慢", "不由自主")
NEGATION_CN_RE = re.compile(
    r"(不|没|没有|无|别|勿|禁止|不要|不得)([^，。；、！？\n]{0,6})(发光|发亮|光效|光斑|亮起|闪光|闪耀|微笑|笑意|空镜|空场)")
NEGATION_EN_RE = re.compile(
    r"\b(no|without|avoid|not|don't|do not)\b[^,.!?;\n]{0,40}?\b(light|glow|smile|smiling|flare|empty shot)\b",
    re.I)

# C9：并列主体句式（实测：模型把并列名词 +「同框」读成画面里有两个主体）
PARALLEL_SUBJECT_RE = re.compile(r"同框|一同入画|同在画面|同时入画|同处一框|in the same frame", re.I)

# C10：抽象过程形态词（模型无法命名的过程形态，只会渲染可命名的具象形态）
VAGUE_FORM_WORDS = ("成线", "成串", "成缕", "如注", "如丝", "如瀑", "轻蜷", "微蜷")


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
    """返回 (errors, warnings, hits)；hits 记录各检查（C1-C10）命中次数，供门日志统计。"""
    errors, warnings = [], []
    hits = {}

    def err(cid, msg):
        errors.append(msg)
        hits[cid] = hits.get(cid, 0) + 1

    def warn(cid, msg):
        warnings.append(msg)
        hits[cid] = hits.get(cid, 0) + 1

    layout = str(data.get("grid_layout", ""))
    shots = data.get("shots")
    if not isinstance(shots, list):
        err("C2", "缺少 shots 数组")
        return errors, warnings, hits

    n = expect_n or LAYOUT_N.get(layout)
    if n is None:
        warn("C2", f"grid_layout={layout!r} 无法推断数量，跳过数量检查")
    elif len(shots) != n:
        err("C2", f"shots 数量 {len(shots)} != 应为 {n}（grid_layout={layout or '未填'}）")

    seen_numbers = {}
    cjk_skip_noted = False
    for i, shot in enumerate(shots, 1):
        tag = f"分镜{i}"
        if not isinstance(shot, dict):
            err("C2", f"{tag}: 不是对象")
            continue
        prompt = shot.get("prompt_text", "")
        num = shot.get("shot_number")
        if not num:
            warn("C7", f"{tag}: 缺 shot_number")
        else:
            if num in seen_numbers:
                err("C7", f"{tag}: shot_number {num!r} 与 {seen_numbers[num]} 重复")
            else:
                seen_numbers[num] = tag
        if len(prompt) > max_chars:
            warn("C4", f"{tag}: 字符数 {len(prompt)} 超上限 {max_chars}（实测超 1600 失败率显著上升，建议拆镜或精简）")
        if cjk_ratio(prompt) >= CJK_SKIP_RATIO:
            if not cjk_skip_noted:
                warn("C3", "检测到中文提示词，词数检查（20-30 英文词）不适用，已跳过")
                cjk_skip_noted = True
        else:
            words = len(prompt.split())
            if not WORD_RANGE[0] <= words <= WORD_RANGE[1]:
                warn("C3", f"{tag}: 词数 {words} 超出 {WORD_RANGE[0]}-{WORD_RANGE[1]}")
        for label, options in REQUIRED_GROUPS:
            if not any(o in prompt for o in options):
                err("C5", f"{tag}: 缺{label}（应含 {' 或 '.join(options[:2])}）")
        for bad in FORBIDDEN:
            if bad.lower() in prompt.lower():
                err("C6", f"{tag}: 含禁用句式 {bad!r}")
        # C8 否定式高关联约束（先剔除无害白名单词，避免「不禁微笑」类误报）
        scan = prompt
        for w in NEGATION_SAFE:
            scan = scan.replace(w, "")
        m = NEGATION_CN_RE.search(scan) or NEGATION_EN_RE.search(scan)
        if m:
            warn("C8", f"{tag}: 否定式高关联约束（词根 {m.group(m.lastindex or 0)!r} 被禁写法）——被禁词根会被模型当画面词渲染，建议改正向描述或换词（见 prompt-craft「否定失效三改法」）")
        # C9 并列主体句式
        m = PARALLEL_SUBJECT_RE.search(prompt)
        if m:
            warn("C9", f"{tag}: 并列主体句式 {m.group(0)!r}——实测易被渲染成两个主体，建议单主体句式（「画面主体：<名>……」）或由站位声明承载")
        # C10 抽象过程形态词
        hit_words = [w for w in VAGUE_FORM_WORDS if w in prompt]
        if hit_words:
            warn("C10", f"{tag}: 抽象过程形态词 {'/'.join(hit_words)}——模型无法命名过程形态，建议改具体可见动作（如「雨滴砸在手背上溅开」）")
    return errors, warnings, hits


def append_gate_log(log_path, file_label, data, errors, warnings, hits):
    """把本次校验结果追加到门日志（写不进去静默跳过，不影响校验）；超上限先轮转（保留最近一半）。"""
    try:
        p = Path(log_path)
        if p.is_file():
            lines = p.read_text(encoding="utf-8").splitlines()
            if len(lines) >= GATE_LOG_MAX_LINES:
                p.write_text("\n".join(lines[GATE_LOG_MAX_LINES // 2:]) + "\n", encoding="utf-8")
        rec = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file": file_label,
            "layout": str(data.get("grid_layout", "")),
            "shots": len(data.get("shots") or []),
            "errors": len(errors),
            "warnings": len(warnings),
            "hits": hits,
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def print_stats(log_path):
    p = Path(log_path)
    if not p.is_file():
        print(f"暂无门日志: {p}（先跑一次校验，或检查 --log-file 路径）")
        return 0
    total = fail = 0
    agg = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        if rec.get("errors"):
            fail += 1
        for k, v in (rec.get("hits") or {}).items():
            agg[k] = agg.get(k, 0) + v
    print(f"门日志 {p}：运行 {total} 次，其中 {fail} 次有错误")
    if agg:
        print("检查命中累计（最常响的检查 = 最该改提示词措辞或复核该规则）：")
        for k, v in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {k}: {v}")
    else:
        print("（无检查命中记录）")
    return 0


def selftest():
    global GATE_LOG_MAX_LINES
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
    e1, _, _ = check(good, None)
    e2, _, _ = check(bad, None)
    e3, w3, _ = check(cn, None)
    e4, _, _ = check(dup, None)
    assert not e1, f"英文正例误报: {e1}"
    assert not e3, f"中文正例误报: {e3}"
    assert not any("分镜" in w and "超出" in w for w in w3), f"中文词数检查未跳过: {w3}"
    assert len(e2) >= 3, f"负例漏报: {e2}"  # 数量 8!=9 + 禁用句式 + 2 组必含词缺失
    assert any("重复" in e for e in e4), f"编号重复未检出: {e4}"
    # 字符上限：超长 prompt 应出现警告
    long_shot = {"grid_layout": "2x2", "shots": [
        {"shot_number": str(i), "prompt_text": good_prompt + " detail" * 250} for i in range(1, 5)]}
    _, w5, _ = check(long_shot, None)
    assert any("字符数" in w for w in w5), f"超长未警告: {w5[:3]}"
    # C8 否定词根：高关联否定式应告警；无害白名单词不应误报
    neg = {"grid_layout": "2x2", "shots": [
        {"shot_number": str(i), "prompt_text": "近景，玉佩不发光，她不禁微笑。" + cn_prompt}
        for i in range(1, 5)]}
    _, w8, h8 = check(neg, None)
    assert any("否定式高关联约束" in w for w in w8), f"C8 未检出: {w8}"
    assert h8.get("C8", 0) >= 1 and not any("不禁" in w for w in w8), f"C8 白名单误报: {w8}"
    # C9 并列主体句式
    par = {"grid_layout": "2x2", "shots": [
        {"shot_number": str(i), "prompt_text": "首帧即这只手与她的脸同框。" + cn_prompt}
        for i in range(1, 5)]}
    _, w9, h9 = check(par, None)
    assert any("并列主体句式" in w for w in w9), f"C9 未检出: {w9}"
    # C10 抽象过程形态词
    vague = {"grid_layout": "2x2", "shots": [
        {"shot_number": str(i), "prompt_text": "漏雨成线砸在手背上。" + cn_prompt}
        for i in range(1, 5)]}
    _, w10, h10 = check(vague, None)
    assert any("抽象过程形态词" in w for w in w10), f"C10 未检出: {w10}"
    # 文件读取路径回归（含围栏与编码回退路径）
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "sb.json"
        f.write_text("```json\n" + json.dumps(good) + "\n```", encoding="utf-8")
        e6, _, _ = check(load(f), None)
        assert not e6, f"文件读取路径误报: {e6}"
        # 门日志：追加 + stats 汇总
        log = Path(tmp) / GATE_LOG_NAME
        errs, warns, hits = check(neg, None)
        append_gate_log(log, "sb.json", neg, errs, warns, hits)
        append_gate_log(log, "sb.json", neg, errs, warns, hits)
        text = log.read_text(encoding="utf-8")
        assert text.count("\n") == 2, f"门日志追加行数异常: {text}"
        rec = json.loads(text.splitlines()[0])
        assert rec["hits"].get("C8", 0) >= 1 and rec["file"] == "sb.json", f"门日志字段异常: {rec}"
        assert print_stats(log) == 0, "stats 读取失败"
        # 门日志轮转：上限调小验证（保留最近一半）
        old_max = GATE_LOG_MAX_LINES
        try:
            GATE_LOG_MAX_LINES = 3
            rot = Path(tmp) / "rot.jsonl"
            for _ in range(6):
                append_gate_log(rot, "f.json", neg, errs, warns, hits)
            n = len(rot.read_text(encoding="utf-8").splitlines())
            assert n <= 3, f"门日志轮转未生效: {n} 行"
        finally:
            GATE_LOG_MAX_LINES = old_max
        missing = print_stats(Path(tmp) / "不存在.jsonl")
        assert missing == 0, "stats 缺文件路径异常"
    print("selftest PASS（英文正例 0 错；中文正例 0 错且词数跳过；负例抓到 %d 错；编号重复检出；超长告警；"
          "C8 否定词根检出且白名单不误报；C9 并列主体检出；C10 抽象形态检出；门日志追加/stats；文件读取通过）"
          % len(e2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="分镜 JSON 文件（容忍 ```json 围栏）")
    ap.add_argument("--n", type=int, choices=(4, 6, 9, 25), help="期望 shots 数量，默认按 grid_layout 推断")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help=f"单条提示词字符上限，默认 {DEFAULT_MAX_CHARS}")
    ap.add_argument("--no-log", action="store_true", help="不追加门日志（默认追加到目标文件同目录 .gate-log.jsonl）")
    ap.add_argument("--log-file", help="门日志路径（默认 <目标文件目录>/.gate-log.jsonl）")
    ap.add_argument("--stats", action="store_true", help="只汇总门日志（哪道检查最常响），不校验文件")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.stats:
        log_path = args.log_file or (Path(args.file).parent / GATE_LOG_NAME if args.file else Path.cwd() / GATE_LOG_NAME)
        return print_stats(log_path)
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

    errors, warnings, hits = check(data, args.n, args.max_chars)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}")
    print("PASS" if not errors else f"FAIL（{len(errors)} 错误 / {len(warnings)} 警告）")
    if not args.no_log:
        log_path = Path(args.log_file) if args.log_file else Path(args.file).parent / GATE_LOG_NAME
        append_gate_log(log_path, Path(args.file).name, data, errors, warnings, hits)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
