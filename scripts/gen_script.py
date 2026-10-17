# -*- coding: utf-8 -*-
"""脚本/文档版本生成引擎（单引擎＋数据文件，替代逐版复制的快照脚本）。

每个版本一个数据文件；引擎按列表顺序执行替换并逐项校验命中数，任一不符即中止
（不写文件）。数据文件里 `src`/`dst` 相对「根目录」解析，根目录约定：

  <root>/tools/gendata/<批次>_vN.json   → 根目录 = <root>
  <root>/gendata/<批次>_vN.json         → 根目录 = <root>
  （不在 gendata 约定位置时以 --root 指定，默认取当前目录）

数据文件结构：
  {src, dst, reps:[{name, old, new, exp}], notes?}
  exp = old 在源稿中的预期命中数（与顺序共同保证唯一性与可回放性）。

用法：
  python gen_script.py <数据文件或简写名>             # 干跑：只列命中数
  python gen_script.py <数据> --apply                # 命中全对才写 dst
  python gen_script.py <数据> --verify               # 回放验收：与现有 dst 逐字节比对
  python gen_script.py --all --verify                # 全部数据文件回放回归
  python gen_script.py --selftest                    # 自检
"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_root(datafile: Path) -> Path:
    g = datafile.parent
    if g.name != "gendata":
        return Path.cwd()
    return g.parent.parent if g.parent.name == "tools" else g.parent


def find_data(name: str):
    cands = [Path(name),
             SCRIPT_DIR / "gendata" / (name + ".json"),
             Path.cwd() / "gendata" / (name + ".json")]
    for c in cands:
        if c.exists():
            return c
    return None


def load(datafile: Path):
    info = json.loads(datafile.read_text(encoding="utf-8"))
    info["_file"] = datafile.name
    return info


def run(info, root: Path, apply=False, verify=False, out=None):
    src = root / info["src"]
    if not src.exists():
        print(f"  !! 源文件不存在: {info['src']}（根目录 {root}）")
        return False
    t = src.read_text(encoding="utf-8")
    bad = []
    for r in info["reps"]:
        c = t.count(r["old"])
        flag = "OK " if c == r["exp"] else "!! "
        if c != r["exp"]:
            bad.append((r["name"], c, r["exp"]))
        print(f"  {flag}[{c}/{r['exp']}] {r['name']}")
        if c == r["exp"]:
            t = t.replace(r["old"], r["new"])
    if bad:
        print("  以下项命中数不符（未写出文件）：")
        for name, c, exp in bad:
            print(f"    {name}: 实际 {c}，预期 {exp}")
        return False

    if verify:
        cur = (root / info["dst"]).read_text(encoding="utf-8")
        if t == cur:
            print(f"  --verify: 回放产物与 {Path(info['dst']).name} 逐字节一致 ✓")
            return True
        print(f"  !! --verify: 有差异（回放 {len(t)} 字符 vs 现存 {len(cur)} 字符）")
        return False
    if out:
        Path(out).write_text(t, encoding="utf-8", newline="\n")
        print(f"  已写出: {out}  chars={len(t)}")
        return True
    if apply:
        (root / info["dst"]).write_text(t, encoding="utf-8", newline="\n")
        print(f"  已写出: {info['dst']}  chars={len(t)}")
        return True
    print("  DRY RUN：全部命中（模拟替换后未写文件，加 --apply 写出）")
    return True


def selftest():
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="gs_st_"))
    try:
        gd = tmp / "gendata"
        gd.mkdir()
        (tmp / "src_v1.md").write_text("标题 v1\n\n第一段。\n\n第二段。\n", encoding="utf-8")
        data = {
            "src": "src_v1.md", "dst": "src_v2.md",
            "reps": [
                {"name": "标题", "old": "标题 v1", "new": "标题 v2", "exp": 1},
                {"name": "段落", "old": "第一段。", "new": "第一段改。", "exp": 1},
            ],
        }
        df = gd / "demo_v2.json"
        df.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assert resolve_root(df) == tmp, "gendata 根解析错误"
        assert run(load(df), tmp, apply=True), "apply 未通过"
        got = (tmp / "src_v2.md").read_text(encoding="utf-8")
        assert got.startswith("标题 v2") and "第一段改。" in got, "产物内容错误"
        assert run(load(df), tmp, verify=True), "verify 未通过"
        bad = {"src": "src_v1.md", "dst": "src_x.md",
               "reps": [{"name": "x", "old": "不存在的文本", "new": "y", "exp": 1}]}
        df2 = gd / "demo_bad.json"
        df2.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(load(df2), tmp) is False, "命中数不符应失败"
        print("selftest PASS（根解析/apply/verify/命中数拦截 四项）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        selftest()
        sys.exit(0)
    root_override = None
    if "--root" in args:
        i = args.index("--root")
        root_override = Path(args[i + 1])
        del args[i:i + 2]
    if "--all" in args:
        dirs = [SCRIPT_DIR / "gendata", Path.cwd() / "gendata"]
        gdir = next((g for g in dirs if g.is_dir() and list(g.glob("*_v*.json"))), None)
        if not gdir:
            print("未找到 gendata/*_v*.json")
            sys.exit(2)
        files = sorted(gdir.glob("*_v*.json"),
                       key=lambda p: int(p.stem.split("_v")[1]))
        okn = 0
        for f in files:
            info = load(f)
            root = root_override or resolve_root(f)
            print(f"[{f.name}] {info['src']} → {info['dst']}")
            if run(info, root, verify="--verify" in args):
                okn += 1
        print(f"回归结果：{okn}/{len(files)} 通过")
        sys.exit(0 if okn == len(files) else 1)

    if not args:
        print(__doc__)
        sys.exit(2)
    datafile = find_data(args[0])
    if not datafile:
        print(f"数据文件不存在: {args[0]}")
        sys.exit(2)
    info = load(datafile)
    root = root_override or resolve_root(datafile)
    print(f"[{datafile.name}] {info['src']}")
    print(f"  → {info['dst']}  （根目录 {root}）")
    if (info.get("notes") or "").strip():
        print(f"  notes: {info['notes'].strip()}")
    ok = run(info, root, apply="--apply" in args, verify="--verify" in args)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
