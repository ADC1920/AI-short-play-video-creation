# -*- coding: utf-8 -*-
"""分镜生成清单（manifest）工具（2026-10-17 建）。

用途：记录每段分镜视频的生成信息（提示词版本、参考图、定稿/候选状态），
供验收前核对「相邻两段是否同源」——混源批次是接缝跳跃的常见结构性来源。

数据文件：<分镜目录>/_manifest.json

用法：
  python tools/manifest.py init <分镜目录> --batch 10.15 [--script-version v21] [--force]
  python tools/manifest.py set  <分镜目录> --shot "LOOK 01" --status 定稿 --script-version v21
  python tools/manifest.py list <分镜目录>
  python tools/manifest.py verify <分镜目录> [--expect-version v21]
  python tools/manifest.py selftest

约定：
  - 只维护元数据，不动视频文件；--status: 定稿/候选/待核（默认 待核）。
  - verify 检查：①同一提示词版本（或与 --expect-version 一致）②状态是否齐为定稿
    ③文件是否仍在目录中；输出不一致清单（退出码 1＝有问题）。
"""
import argparse
import json
import sys
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

MANIFEST_NAME = "_manifest.json"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_dir(d: Path):
    mf = d / MANIFEST_NAME
    if not mf.exists():
        print(f"未找到清单 {mf}（先跑 init）")
        sys.exit(2)
    return mf, json.loads(mf.read_text(encoding="utf-8"))


def save(mf: Path, data: dict):
    data["updated"] = now()
    mf.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8", newline="\n")


def scan(d: Path, pattern: str):
    files = sorted([p for p in d.glob(pattern) if p.is_file()])
    # 开场排最前（"LOOK  0" 字符串序本就在前，此处再兜底）
    files.sort(key=lambda p: (0 if "0" in p.stem[:8] and "开场" in p.stem else 1, p.name))
    return files


def cmd_init(args):
    d = Path(args.dir)
    mf = d / MANIFEST_NAME
    if mf.exists() and not args.force:
        print(f"清单已存在：{mf}（要重建加 --force）")
        sys.exit(2)
    shots = []
    for i, p in enumerate(scan(d, args.pattern), 1):
        shots.append({
            "order": i,
            "shot": p.stem,
            "file": p.name,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "script_version": args.script_version or "",
            "refs": [],
            "status": "待核",
            "note": "",
        })
    data = {"batch": args.batch or "", "script_version": args.script_version or "",
            "updated": now(), "shots": shots}
    save(mf, data)
    print(f"已建清单：{mf}（{len(shots)} 段）")


def find_shot(data, key: str):
    for s in data["shots"]:
        if s["shot"] == key or s["file"] == key or s["shot"].startswith(key):
            return s
    return None


def cmd_set(args):
    mf, data = load_dir(Path(args.dir))
    s = find_shot(data, args.shot)
    if not s:
        print(f"未找到：{args.shot}（可用 list 查看）")
        sys.exit(2)
    for k, v in [("script_version", args.script_version), ("status", args.status),
                 ("note", args.note)]:
        if v is not None:
            s[k] = v
    if args.refs is not None:
        s["refs"] = [x for x in args.refs.split(";") if x]
    save(mf, data)
    print(f"已更新 {s['shot']}：version={s['script_version']} status={s['status']}")


def cmd_list(args):
    _, data = load_dir(Path(args.dir))
    print(f"批次 {data.get('batch','')}  脚本版本 {data.get('script_version','')}  更新 {data.get('updated','')}")
    for s in data["shots"]:
        print(f"  {s['order']:>2}  {s['shot']:<24} {s['status']:<4} v={s['script_version'] or '-':<6} {s['mtime']}  refs={len(s['refs'])}")


def cmd_verify(args):
    d = Path(args.dir)
    mf, data = load_dir(d)
    expect = args.expect_version or data.get("script_version") or ""
    issues = []
    versions = {}
    for s in data["shots"]:
        fp = d / s["file"]
        if not fp.exists():
            issues.append(f"文件缺失：{s['shot']} → {s['file']}")
        v = s["script_version"] or "(未记)"
        versions.setdefault(v, []).append(s["shot"])
        if s["status"] != "定稿":
            issues.append(f"非定稿：{s['shot']}（{s['status']}）")
        if expect and v != expect:
            issues.append(f"版本不符：{s['shot']} 记 {v}，期望 {expect}")
    print(f"清单 {mf}  批次 {data.get('batch','')}  共 {len(data['shots'])} 段")
    print("版本分布：" + "；".join(f"{v}×{len(vs)}" for v, vs in versions.items()))
    if issues:
        print(f"\n同源核对：{len(issues)} 项待处理——")
        for it in issues:
            print("  -", it)
        sys.exit(1)
    print("\n同源核对：通过（全部定稿、版本一致、文件在位）")


def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="mf_st_"))
    try:
        for n in ["LOOK  0 · 开场.mp4", "LOOK 01 · 甲.mp4", "LOOK 02 · 乙.mp4"]:
            (tmp / n).write_bytes(b"stub")
        ns = argparse.Namespace(dir=str(tmp), pattern="*.mp4", batch="test",
                                script_version="v21", force=False)
        cmd_init(ns)
        _, data = load_dir(tmp)
        assert len(data["shots"]) == 3 and data["shots"][0]["shot"].startswith("LOOK  0"), "初始化排序错误"
        ns2 = argparse.Namespace(dir=str(tmp), shot="LOOK 01", script_version=None,
                                 status="定稿", note="优选第 2 次", refs="a.jpg;b.jpg")
        cmd_set(ns2)
        _, data = load_dir(tmp)
        s = find_shot(data, "LOOK 01")
        assert s["status"] == "定稿" and s["refs"] == ["a.jpg", "b.jpg"], "set 未生效"
        # verify 应因未全定稿而失败（exit 1）
        import contextlib, io
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cmd_verify(argparse.Namespace(dir=str(tmp), expect_version="v21"))
            raise AssertionError("verify 应报 2 项非定稿")
        except SystemExit as e:
            assert e.code == 1, f"verify 退出码应为 1，实际 {e.code}"
        print("selftest PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if "--selftest" in sys.argv[1:]:
        selftest()
        return
    ap = argparse.ArgumentParser(description="分镜生成清单（manifest）工具")
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("init", help="扫描目录建清单")
    p1.add_argument("dir"); p1.add_argument("--pattern", default="*.mp4")
    p1.add_argument("--batch", default=""); p1.add_argument("--script-version", default="")
    p1.add_argument("--force", action="store_true")
    p2 = sub.add_parser("set", help="更新条目")
    p2.add_argument("dir"); p2.add_argument("--shot", required=True)
    p2.add_argument("--script-version"); p2.add_argument("--status"); p2.add_argument("--note")
    p2.add_argument("--refs", help="分号分隔的参考图清单")
    p3 = sub.add_parser("list", help="列出清单"); p3.add_argument("dir")
    p4 = sub.add_parser("verify", help="同源核对")
    p4.add_argument("dir"); p4.add_argument("--expect-version", default="")
    p5 = sub.add_parser("selftest", help="自检")
    args = ap.parse_args()
    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "set":
        cmd_set(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "verify":
        cmd_verify(args)
    elif args.cmd == "selftest":
        selftest()
    else:
        ap.print_help()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
