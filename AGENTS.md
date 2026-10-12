# 项目级 Agent 规则 · AI-short-play-video-creation

> 本文件是项目级注入（每会话自动进入）：只管「本项目特有信息 + 承载指针」，通用义务不复述（单一权威=注入核心）。由工作流「项目承载检查」创建（2026-10-12）。

## 回指（强制字段）
- 完整纪律（判级/红线/必问/开工四步/GATE/检索端口）权威=注入核心与 SKILL.md；按需以 Skill 工具加载「shisan-xinuo-workflow」（注册名），本文件在场但 Skill 未在场 → 先加载再继续。
- 会话末：更新 `memory/agent-log.md`（流水区+状态段）后离开——不更新=交接断链。

## 迷你流程骨架（注入核心缺席时的最小执行序）
- 开工四步：复述 → 承载检查 → 记忆对齐（读 agent-log 状态段一屏）→ 判级（L1 直做 / L2 记录做 / L3 先问）。
- 每轮首产物=复述（新任务全量三行；追加/继续一行）；状态行 `Context: state=… L=… confirm=…`。
- 收尾：GATE 单行 12 字段；agent-log 流水一行+状态段刷新。
- 红线三条：密钥绝不落盘｜重大改动先回滚点｜不假实现（未验证显式标注）。

## 项目纪律（本项目特有）
- **仓库定位**：公开技能仓库——发布物=技能本体（`SKILL.md` / `references/` / `scripts/` / `README.md` / `CHANGELOG.md` / `LICENSE`）；`memory/` 为本地承载（已从版本控制排除），`docs/` 为开发导航。
- **版本与提交**：版本号落 `CHANGELOG.md`（SKILL.md front-matter `version` 同步）；提交遵守仓库惯例 `<类型>(<范围>):〈动词开头描述〉`（如 `feat(skill): v1.6.0 …`，类型前缀跟随历史 feat/fix/docs/refactor/chore）；push=对外发布（L3，须用户确认）。
- **验证基线**：改动技能后跑四脚本自检 `python scripts/validate_storyboard.py --selftest`（另三件 check_refs/init_project/make_grid 同法）全过再提交；`make_grid.py` 需 Pillow。
- **技能实体同步面**：本工作区=开发源；本机技能实体 `C:\Users\ADC\.agents\skills\ai-short-play-video-creation` 为静态复制（非 git），发版后需手动同步（先备份；回滚点落 `~\.agents\skill-backups\`）。同步口径=技能面文件（SKILL.md/references/scripts/README/CHANGELOG/LICENSE/.git*）；承载文件（AGENTS.md/docs/memory）不入实体。已于 2026-10-12 同步至 v1.7.0（v1.6.0 → v1.7.0，含 md5 全量核对）。
- 权威源顺序：注入核心 → shisan-xinuo-workflow SKILL.md → 本文件 → `docs/project-info.md`。

## 项目承载（已就绪）
- `memory/agent-log.md`：一档制四区（状态段/教训区/偏好段/流水区；本地留档，不入库）。
- `docs/project-info.md`：六节索引（模块表带关键词锚定列，细则 #275）。
