#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多集项目脚手架（ai-short-play-video 技能）。

一键生成多集漫剧项目的标准结构：
    <项目>/
      素材/                     全剧共用素材（文件名 = @ 引用名）
      第1集/剧本.md + 分镜/ + 成片/
      第2集/...
      ...（按 --episodes 数量）

幂等：已存在的目录/文件不覆盖、不重建，重复运行为安全空操作。

用法:
    python init_project.py <项目目录> [--episodes N]
    python init_project.py --selftest
退出码: 0=成功, 2=用法错误
"""
import argparse
import sys
import tempfile
from pathlib import Path

EPISODE_TEMPLATE = """# 第{ep}集 剧本

（本集剧本：按剧情节点切分，每集有独立的钩子与收尾。出场角色/场景用 @ 引用名。）
"""

TAIL_TEMPLATE = """# 第{ep}集 尾帧描述

（本集成片末帧画面一句话描述，供下一集首镜衔接引用。）
"""


def init_project(root, episodes):
    root = Path(root)
    created, skipped = [], []

    def ensure(p):
        p = Path(p)
        if p.exists():
            skipped.append(str(p))
            return False
        p.mkdir(parents=True, exist_ok=True)
        created.append(str(p))
        return True

    def ensure_file(p, content):
        p = Path(p)
        if p.exists():
            skipped.append(str(p))
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        created.append(str(p))

    ensure(root)
    ensure(root / "素材")
    for ep in range(1, episodes + 1):
        ep_dir = root / f"第{ep}集"
        ensure(ep_dir)
        ensure(ep_dir / "分镜")
        ensure(ep_dir / "成片")
        ensure_file(ep_dir / "剧本.md", EPISODE_TEMPLATE.format(ep=ep))
        ensure_file(ep_dir / "分镜" / "尾帧.md", TAIL_TEMPLATE.format(ep=ep))

    print(f"项目：{root}")
    print(f"创建 {len(created)} 项，跳过（已存在）{len(skipped)} 项：")
    for c in created:
        print(f"  + {Path(c).relative_to(root) if Path(c) != root else '.'}")
    return 0


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "我的漫剧"
        rc = init_project(root, 3)
        assert rc == 0
        # 结构断言
        assert (root / "素材").is_dir()
        for ep in range(1, 4):
            assert (root / f"第{ep}集" / "剧本.md").is_file()
            assert (root / f"第{ep}集" / "分镜").is_dir()
            assert (root / f"第{ep}集" / "成片").is_dir()
            assert (root / f"第{ep}集" / "分镜" / "尾帧.md").is_file()
        assert not (root / "第4集").exists(), "episodes=3 不应创建第4集"
        # 幂等：改内容后重跑，内容不被覆盖
        marker = "已有内容不覆盖"
        (root / "第1集" / "剧本.md").write_text(marker, encoding="utf-8")
        init_project(root, 3)
        assert (root / "第1集" / "剧本.md").read_text(encoding="utf-8") == marker, "重跑覆盖了已有内容"
        # 扩容：episodes=5 时补建 4/5 集
        init_project(root, 5)
        assert (root / "第5集" / "剧本.md").is_file(), "扩容未补建"
    print("selftest PASS（3 集结构 / 幂等不覆盖 / 扩容补建）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?", help="项目目录（不存在则创建）")
    ap.add_argument("--episodes", type=int, default=1, help="集数，默认 1")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.project:
        ap.print_help()
        return 2
    if args.episodes < 1:
        print("--episodes 必须 ≥1")
        return 2
    return init_project(args.project, args.episodes)


if __name__ == "__main__":
    sys.exit(main())
