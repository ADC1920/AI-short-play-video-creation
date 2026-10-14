# -*- coding: utf-8 -*-
"""旧版 docx 自动归档工具（交付版本管理）

用途：docx 成品交付项目里把「当前版」留在交付根目录、把历史版本移入 `_旧版归档\\`（移动非删除、可回滚）。
配套条款见 SKILL.md「成本与确认纪律 · 交付版本管理」。

用法：
    python scripts/archive_old_docx.py <交付文件夹> "当前版文件名.docx" ["第二保留文件名.docx" ...] [--dry-run]
    python scripts/archive_old_docx.py --selftest

规则：
- 交付文件夹【根目录】下的 *.docx 中，不在「保留清单」里的全部移入 <交付文件夹>/_旧版归档/
- 保留清单里的文件（当前版）原地不动；子目录不扫描
- 移动非删除；重名时自动加 _2/_3… 后缀避免覆盖
- 文件被占用（Word 等程序打开中）时：不产生残余副本、跳过该文件并计入失败，其余文件继续处理
- 先 --dry-run 预览是推荐做法
"""
import sys
import shutil
import io
import tempfile
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass


def parse_args(argv):
    dry = "--dry-run" in argv
    selftest = "--selftest" in argv
    args = [a for a in argv if a not in ("--dry-run", "--selftest")]
    return args, dry, selftest


def archive(folder: Path, keep, dry=False):
    """归档；返回 (归档成功数, 保留数, 失败清单)。参数错误抛 ValueError。"""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("交付文件夹不存在: %s" % folder)
    for k in keep:
        if not (folder / k).is_file():
            raise ValueError("保留清单里的文件不存在: %s" % (folder / k))
    archive_dir = folder / "_旧版归档"
    docs = sorted(p for p in folder.glob("*.docx") if p.is_file())
    todo = [p for p in docs if p.name not in keep]
    if not todo:
        print("无需归档：根目录仅有当前版 docx（%s）" % "、".join(keep))
        return 0, len(keep), []
    if not dry:
        archive_dir.mkdir(exist_ok=True)
    failed = []
    moved = 0
    for p in todo:
        dest = archive_dir / p.name
        if dest.exists():
            i = 2
            while True:
                cand = archive_dir / (p.stem + "_%d" % i + p.suffix)
                if not cand.exists():
                    dest = cand
                    break
                i += 1
        if dry:
            print("[dry-run] 将归档: %s -> _旧版归档/%s" % (p.name, dest.name))
            moved += 1
            continue
        try:
            shutil.move(str(p), str(dest))
            print("已归档: %s -> _旧版归档/%s" % (p.name, dest.name))
            moved += 1
        except OSError as e:
            # 被占用等场景：撤销 move 可能已产生的残余副本（源文件仍在原处）
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            print("!! 归档失败（文件可能正被 Word 等程序打开，请关闭后重试）: %s" % p.name)
            failed.append(p.name)
    tail = "，失败 %d 件（被占用）" % len(failed) if failed else ""
    print("完成：归档 %d 件，保留当前版 %d 件%s" % (moved, len(keep), tail))
    return moved, len(keep), failed


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "a.docx").write_bytes(b"a")
        (d / "b.docx").write_bytes(b"b")
        (d / "note.txt").write_text("x", encoding="utf-8")
        # 1) 常规归档：保留 b，a 入档
        n, _, f = archive(d, {"b.docx"})
        if n != 1 or f or not (d / "_旧版归档" / "a.docx").exists() or not (d / "b.docx").exists():
            print("FAIL: 常规归档"); ok = False
        # 2) 非 docx 不动
        if not (d / "note.txt").exists():
            print("FAIL: 非 docx 被误动"); ok = False
        # 3) 重名加后缀
        (d / "a.docx").write_bytes(b"a2")
        n, _, f = archive(d, {"b.docx"})
        if not (d / "_旧版归档" / "a_2.docx").exists():
            print("FAIL: 重名未加后缀"); ok = False
        # 4) 保留清单缺文件应报错
        try:
            archive(d, {"nonexist.docx"})
            print("FAIL: 缺失保留文件未报错"); ok = False
        except ValueError:
            pass
        # 5) dry-run 不移动
        (d / "c.docx").write_bytes(b"c")
        archive(d, {"b.docx"}, dry=True)
        if not (d / "c.docx").exists():
            print("FAIL: dry-run 移动了文件"); ok = False
        # 6) 占用场景：不产生残余副本、源保留、计入失败
        (d / "d.docx").write_bytes(b"d")
        fh = open(d / "d.docx", "rb")
        try:
            n, _, f = archive(d, {"b.docx"})
            if "d.docx" in f:
                if not (d / "d.docx").exists():
                    print("FAIL: 占用文件被移走"); ok = False
                if (d / "_旧版归档" / "d.docx").exists():
                    print("FAIL: 占用文件留有残余副本"); ok = False
            else:
                print("SKIP: 本平台未锁定被打开文件（占用用例跳过）")
        finally:
            fh.close()
        # 清理占用用例残留（若移动成功）
        for cand in (d / "d.docx", d / "_旧版归档" / "d.docx"):
            if cand.exists():
                cand.unlink()
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    args, dry, selftest_flag = parse_args(sys.argv[1:])
    if selftest_flag:
        sys.exit(selftest())
    if len(args) < 2:
        print(__doc__)
        sys.exit(2)
    try:
        _, _, failed = archive(Path(args[0]), set(args[1:]), dry=dry)
        sys.exit(1 if failed else 0)
    except ValueError as e:
        print("!!", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
