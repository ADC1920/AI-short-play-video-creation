#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能实体同步（开发源 → 技能实体部署目录）。

把技能面文件从开发源同步到技能实体（静态复制目录），一条链：
  1) 安全检查（源必须是技能根；目标不存在则新建，已存在必须含 SKILL.md，拒绝误指路径）
  2) 差异扫描（新增 / 更新 / 相同 / 目标多余）
  3) 备份目标目录到备份目录（时间戳快照；备份失败即中止）
  4) 同步（默认只发新增与更新；--prune 才删除目标多余件）
  5) 复核（重扫差异面，要求技能面零差异）

排除项 EXCLUDE（承载文件与仓库级资产，不入实体）：.git / AGENTS.md / docs / memory / .github / examples
（新增这类内容时把顶层名加进脚本顶部 EXCLUDE 常量。）

用法:
    python sync_entity.py <目标目录> [--source <源目录>] [--backup-dir <目录>] [--dry-run] [--prune]
    python sync_entity.py --selftest
退出码: 0=完成且复核通过, 1=复核仍有差异, 2=用法/安全检查失败
"""
import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

EXCLUDE = {".git", "AGENTS.md", "docs", "memory", ".github", "examples"}
MAX_LIST = 20  # 差异清单每类最多打印条数


def file_map(root):
    """{相对路径(posix): 绝对路径}；剪掉 EXCLUDE 顶层项。"""
    out = {}
    root = Path(root)
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir.parts:
            if rel_dir.parts[0] in EXCLUDE:
                dirnames[:] = []
                continue
        else:
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE]
        for f in filenames:
            rel = rel_dir / f
            if rel.parts[0] in EXCLUDE:
                continue
            out[rel.as_posix()] = Path(dirpath) / f
    return out


def md5(p):
    h = hashlib.md5()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def scan(src_map, dst_map):
    """返回 (added, updated, same, extra)。"""
    added, updated, same = [], [], []
    for rel, sp in src_map.items():
        dp = dst_map.get(rel)
        if dp is None:
            added.append(rel)
        elif md5(sp) != md5(dp):
            updated.append(rel)
        else:
            same.append(rel)
    extra = sorted(set(dst_map) - set(src_map))
    return sorted(added), sorted(updated), sorted(same), extra


def print_list(title, items):
    if not items:
        return
    print(f"{title}（{len(items)}）:")
    for it in items[:MAX_LIST]:
        print(f"  - {it}")
    if len(items) > MAX_LIST:
        print(f"  … 其余 {len(items) - MAX_LIST} 条省略")


def safety_check(src_root, dst_root):
    errs = []
    if not (Path(src_root) / "SKILL.md").is_file():
        errs.append(f"源目录不是技能根（缺 SKILL.md）: {src_root}")
    if Path(dst_root).resolve() == Path(src_root).resolve():
        errs.append("目标目录与源目录相同")
    if Path(dst_root).exists() and not (Path(dst_root) / "SKILL.md").is_file():
        errs.append(f"目标目录已存在但不是技能实体（缺 SKILL.md），拒绝覆盖: {dst_root}")
    return errs


def run(target, source=None, backup_dir=None, dry_run=False, prune=False):
    src_root = Path(source).resolve() if source else Path(__file__).resolve().parent.parent
    dst_root = Path(target).resolve()
    errs = safety_check(src_root, dst_root)
    if errs:
        for e in errs:
            print(f"安全检查失败: {e}")
        return 2

    src_map = file_map(src_root)
    dst_map = file_map(dst_root)
    added, updated, same, extra = scan(src_map, dst_map)
    print(f"技能面: 源 {len(src_map)} 件 | 目标 {len(dst_map)} 件")
    print(f"差异面: 新增 {len(added)} / 更新 {len(updated)} / 相同 {len(same)} / 目标多余 {len(extra)}")
    print_list("新增", added)
    print_list("更新", updated)
    print_list("目标多余（默认保留，--prune 删除）", extra)

    if dry_run:
        print("dry-run：未写入任何文件。")
        return 0
    if not added and not updated and (not prune or not extra):
        print("无需同步（技能面已一致）。")
        return 0

    # 备份（失败即中止，不进入写入阶段）
    bdir = None
    if dst_root.is_dir():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = Path(backup_dir) if backup_dir else Path.home() / ".agents" / "skill-backups"
        bdir = base / f"{ts}-{dst_root.name}-pre-sync"
        n = 2
        while bdir.exists():  # 同秒连续同步时防重名
            bdir = base / f"{ts}-{dst_root.name}-pre-sync-{n}"
            n += 1
        try:
            base.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dst_root, bdir)
        except OSError as exc:
            print(f"备份失败，已中止同步: {exc}")
            return 2
        print(f"备份完成: {bdir}")

    for rel in added + updated:
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_map[rel], dst)
    removed = []
    if prune:
        for rel in extra:
            try:
                (dst_root / rel).unlink()
                removed.append(rel)
            except OSError as exc:
                print(f"删除失败 {rel}: {exc}")
    print(f"同步完成: 写入 {len(added) + len(updated)} 件" + (f" | 删除 {len(removed)} 件" if removed else ""))

    # 复核
    src_map2 = file_map(src_root)
    dst_map2 = file_map(dst_root)
    added2, updated2, _, extra2 = scan(src_map2, dst_map2)
    if added2 or updated2 or (prune and extra2):
        print(f"复核未通过: 新增残差 {len(added2)} / 更新残差 {len(updated2)}" + (f" / 多余残差 {len(extra2)}" if prune else ""))
        return 1
    print(f"复核通过: 技能面 {len(src_map2)} 件全等（md5 逐件核对）。" + (f" 目标多余 {len(extra2)} 件（未删，--prune 可清）。" if extra2 and not prune else ""))
    return 0


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src, dst, bak = root / "src", root / "dst", root / "backups"
        (src / "references").mkdir(parents=True)
        (src / "scripts").mkdir()
        (src / "docs").mkdir()
        (src / "memory").mkdir()
        (src / "examples").mkdir()
        (src / "SKILL.md").write_text("v2", encoding="utf-8")
        (src / "references" / "a.md").write_text("new-a", encoding="utf-8")
        (src / "references" / "b.md").write_text("new-b", encoding="utf-8")
        (src / "scripts" / "s.py").write_text("same", encoding="utf-8")
        (src / "AGENTS.md").write_text("bearer", encoding="utf-8")
        (src / "docs" / "x.md").write_text("docs", encoding="utf-8")
        (src / "memory" / "y.md").write_text("mem", encoding="utf-8")
        (src / "examples" / "e.md").write_text("ex", encoding="utf-8")
        (dst / "references").mkdir(parents=True)
        (dst / "scripts").mkdir()
        (dst / "SKILL.md").write_text("v1", encoding="utf-8")
        (dst / "references" / "a.md").write_text("old-a", encoding="utf-8")
        (dst / "scripts" / "s.py").write_text("same", encoding="utf-8")
        (dst / "references" / "stale.md").write_text("stale", encoding="utf-8")

        assert run(str(dst), source=str(src), backup_dir=str(bak), dry_run=True) == 0
        assert (dst / "SKILL.md").read_text(encoding="utf-8") == "v1", "dry-run 不应写入"
        assert run(str(dst), source=str(src), backup_dir=str(bak)) == 0
        assert (dst / "SKILL.md").read_text(encoding="utf-8") == "v2", "更新未生效"
        assert (dst / "references" / "b.md").exists(), "新增未生效"
        assert not (dst / "AGENTS.md").exists(), "排除件被误同步"
        assert not (dst / "docs").exists() and not (dst / "memory").exists() and not (dst / "examples").exists(), "排除目录被误同步"
        assert (dst / "references" / "stale.md").exists(), "默认不应删除多余件"
        assert bak.is_dir() and any(bak.iterdir()), "备份未生成"
        assert run(str(dst), source=str(src), backup_dir=str(bak), prune=True) == 0
        assert not (dst / "references" / "stale.md").exists(), "prune 未删除多余件"
        bad = root / "bad"
        bad.mkdir()
        assert run(str(bad), source=str(src), backup_dir=str(bak)) != 0, "非技能实体目标未被拒绝"
    print("selftest PASS（差异扫描 / 备份 / dry-run 不写 / 新增与更新 / 排除件未动 / "
          "多余件默认保留 / prune 删除 / 非实体目标拒绝 / 复核通过）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="技能实体同步（开发源 → 技能实体部署目录）")
    ap.add_argument("target", nargs="?", help="目标技能实体目录")
    ap.add_argument("--source", help="源目录（默认=本脚本所在技能根）")
    ap.add_argument("--backup-dir", help="备份目录（默认 ~/.agents/skill-backups）")
    ap.add_argument("--dry-run", action="store_true", help="只报差异面，不写入")
    ap.add_argument("--prune", action="store_true", help="删除目标侧技能面多余件（默认保留）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.target:
        ap.print_help()
        return 2
    return run(args.target, args.source, args.backup_dir, args.dry_run, args.prune)


if __name__ == "__main__":
    sys.exit(main())
