#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能双根核对：内容一致性 + 硬链完整性核对与修复。

适用场景：同一技能以「硬链同源」部署在两个技能根（如 `.zcode` 与 `.agents`）。
`sync_entity.py` 只做单目标内容同步——新增文件在两个根会各自复制、断链；
本工具作为其固定收尾步：逐件核对内容（md5）与硬链（samefile），`--fix` 时
只修「内容相同但非硬链」的右根文件（以左根为目标重建硬链）；内容不一致
只报告、不修复（需人工判断以哪侧为准）。

默认双根（不给参数时）：由脚本位置推导——脚本位于
`<home>/.zcode|.agents/skills/<技能>/scripts/` 时，脚本所在侧为左根，
同名技能在另一侧为右根；非标准布局请显式传左右根。

用法:
    python check_double_root.py [左根] [右根] [--fix]
    python check_double_root.py --selftest
退出码: 0=一致；1=有差异（或修复后仍有残留）；2=用法或路径检查失败
"""
import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path


def default_roots():
    """由脚本位置推导默认双根；非标准布局返回 (None, None)。"""
    here = Path(__file__).resolve()
    if here.parent.name != "scripts":
        return None, None
    skill_dir = here.parent.parent          # <base>/skills/<技能>
    base = skill_dir.parent                 # <base>/skills
    home = Path.home().resolve()
    pairs = ((home / ".zcode" / "skills", home / ".agents" / "skills"),
             (home / ".agents" / "skills", home / ".zcode" / "skills"))
    for this_side, other_side in pairs:
        try:
            if base.resolve() == this_side:
                return skill_dir, other_side / skill_dir.name
        except OSError:
            continue
    return None, None


def tree(root):
    """{相对路径(posix): 绝对路径}。"""
    out = {}
    root = Path(root)
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            p = Path(dirpath) / f
            out[p.relative_to(root).as_posix()] = p
    return out


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compare(left, right):
    """返回 (linked, need_fix, problems)；problems=[(rel, 描述)]。"""
    lf, rf = tree(left), tree(right)
    linked, need_fix, problems = [], [], []
    for rel in sorted(set(lf) | set(rf)):
        lp, rp = lf.get(rel), rf.get(rel)
        if lp is None or rp is None:
            problems.append((rel, "仅单侧存在（左" + ("有" if lp else "无") + " / 右" + ("有" if rp else "无") + "）"))
            continue
        if md5(lp) != md5(rp):
            problems.append((rel, "内容不一致"))
            continue
        try:
            if os.path.samefile(lp, rp):
                linked.append(rel)
            else:
                need_fix.append(rel)
        except OSError:
            need_fix.append(rel)
    return linked, need_fix, problems


def relink(left, right, rels):
    """右根以左根为目标重建硬链；返回 (已修, 失败[(rel,原因)])。"""
    lf, rf = tree(left), tree(right)
    ok, bad = [], []
    for rel in rels:
        tmp = rf[rel].with_name(rf[rel].name + ".relink-tmp")
        try:
            if tmp.exists():
                tmp.unlink()
            os.link(lf[rel], tmp)
            os.replace(tmp, rf[rel])
            ok.append(rel)
        except OSError as exc:
            bad.append((rel, str(exc)))
            if tmp.exists():
                tmp.unlink()
    return ok, bad


def run(left, right, do_fix):
    for side, root in (("左根", left), ("右根", right)):
        if not (Path(root) / "SKILL.md").is_file():
            print(f"{side}不是技能实体（缺 SKILL.md）: {root}")
            return 2
    linked, need_fix, problems = compare(left, right)
    total = len(linked) + len(need_fix) + len(problems)
    print(f"全量 {total} 件: 硬链 {len(linked)} / 待修硬链 {len(need_fix)} / 问题 {len(problems)}")
    for rel in need_fix:
        print(f"  待修: {rel}")
    for rel, why in problems:
        print(f"  问题: {rel} -> {why}")
    if not do_fix:
        return 1 if (need_fix or problems) else 0
    if need_fix:
        ok, bad = relink(left, right, need_fix)
        print(f"修复完成: {len(ok)} 件" + (f" / 失败 {len(bad)}" if bad else ""))
        for rel, why in bad:
            print(f"  修复失败: {rel} -> {why}")
        linked2, need_fix2, _ = compare(left, right)
        if need_fix2:
            print(f"复核未通过: 仍有 {len(need_fix2)} 件非硬链")
            return 1
        print(f"复核通过: {len(linked2)} 件全硬链")
    return 1 if problems else 0


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        left, right = Path(tmp) / "left", Path(tmp) / "right"
        left.mkdir()
        right.mkdir()
        (left / "SKILL.md").write_text("x", encoding="utf-8")
        (right / "SKILL.md").write_text("x", encoding="utf-8")   # 内容同、非链 → 待修
        (left / "a.txt").write_text("A", encoding="utf-8")
        os.link(left / "a.txt", right / "a.txt")                 # 硬链 → OK
        (left / "c.txt").write_text("C1", encoding="utf-8")
        (right / "c.txt").write_text("C2", encoding="utf-8")     # 内容不同 → 问题
        (left / "only.txt").write_text("L", encoding="utf-8")    # 仅左 → 问题

        linked, need_fix, problems = compare(left, right)
        assert "a.txt" in linked, "硬链件识别失败"
        assert need_fix == ["SKILL.md"], f"待修识别失败: {need_fix}"
        assert len(problems) == 2, f"问题识别失败: {problems}"
        ok, bad = relink(left, right, need_fix)
        assert not bad and ok == ["SKILL.md"], "修复失败"
        assert os.path.samefile(left / "SKILL.md", right / "SKILL.md"), "复核失败: 未成硬链"
        assert (right / "c.txt").read_text(encoding="utf-8") == "C2", "修复不应触碰内容不一致件"
        assert not (right / "only.txt").exists(), "修复不应为单侧件创建副本"
        print("selftest PASS（硬链识别 / 待修识别 / 问题识别 / 修复成链 / 不一致件未触碰 / 单侧件未创建）")
        return 0


def main():
    ap = argparse.ArgumentParser(description="技能双根核对：内容一致性 + 硬链完整性核对与修复")
    ap.add_argument("left", nargs="?", help="左根（修复时以此为物理文件目标；缺省由脚本位置推导）")
    ap.add_argument("right", nargs="?", help="右根（待修硬链侧；缺省由脚本位置推导）")
    ap.add_argument("--fix", action="store_true", help="修复右根「内容相同但非硬链」的文件")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    left, right = args.left, args.right
    if not left and not right:
        left, right = default_roots()
        if not left:
            print("未给出左右根，且脚本不在 <home>/.zcode|.agents/skills/<技能>/scripts/ 标准布局下，无法推导默认双根。")
            print("用法: python check_double_root.py <左根> <右根> [--fix]")
            return 2
        print(f"默认双根（由脚本位置推导）: 左={left} | 右={right}")
    elif not (left and right):
        print("左右根需成对给出（或都不给以推导默认）。")
        return 2
    return run(left, right, args.fix)


if __name__ == "__main__":
    sys.exit(main())
