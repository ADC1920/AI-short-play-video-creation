# ai-short-play-video-creation · AI 短剧创作工作流

把剧本或一句剧情梗概做成 AI 短剧视频。覆盖分镜、素材、逐镜生成、配音和后期拼接，动态漫、漫剧、写实风都适用，出片以即梦 Seedance 为主。整套技能按 Agent Skill 机制组织，Claude Code、ZCode、Codex 等可以直接安装使用。

## 快速上手

1. **有完整剧本**：走路线 A（分镜智能体）。把 `references/agent-prompt.md` 里的系统提示词贴进对话助手，输入剧本，得到工程级分镜蓝图（镜号、时长、转场、声音设计），再按蓝图逐镜出图、出视频。
2. **只有一句话梗概**：走路线 B（宫格分镜直生）。生成宫格分镜 JSON（可机检），用 `python scripts/make_grid.py -o grid.png <图片目录>` 拼成宫格图，一张图直出 15 秒视频。
3. **人物参考图过不了人脸审核**：走路线 C 的五种规避法（墨镜遮挡、网格遮挡、无五官三视图、服装+头部组合、风格转绘），可叠加在 A、B 上。
4. **长剧或小说改编**：走多集工作流，先分集，再逐集套用 A 或 B，素材全剧共用一套。

写提示词之前，建议先过一遍 SKILL.md 的「铁律与核心公式」；生成或拼接出问题时，先查「排障速查」表。剧本之外还有一批常用工艺，入口都在 `references/`：多人戏站位与轴线、打戏预演、微表情、情绪节拍与开场钩子、参考视频对标、段缝衔接、声音与配音。

## 仓库结构

| 位置 | 内容 |
|---|---|
| `SKILL.md` | 主入口：三条路线、对标参考流程、铁律与核心公式、平台硬约束、成本与确认纪律、排障速查、多集工作流，以及完整的文件与脚本索引 |
| `references/` | 13 篇工艺文档：分镜智能体系统提示词、宫格直生、人脸规避、素材一致性、分镜图工艺、提示词进阶、衔接与后期、连续性台账、声音配音、即梦 Seedance 2.5 实测、微表情、情绪钩子、打戏预演 |
| `scripts/` | 9 个工程脚本：分镜 JSON 机检、拼宫格、@引用核对、多集脚手架、旧版归档、实体同步、双根核对、接缝量化检测、docx 分页修复 |
| `examples/demo-multi-ep/` | 最小多集样例（占位素材、剧本、分镜 JSON），可以拿来参照，也用作回归测试 |
| `docs/` | 工作区索引（project-info）与技能更新说明 |
| `AGENTS.md` · `CHANGELOG.md` · `LICENSE` | 维护口径、版本记录、MIT 协议 |
| `.github/workflows/selftest.yml` | CI：push 时自动跑九个脚本自检，加上样例项目的端到端回归 |

脚本逐个的说明见 SKILL.md 的「参考文件与脚本索引」。

## 安装

克隆到 Agent 的技能根目录，目录名保持 `ai-short-play-video-creation`：

```bash
# Linux / macOS / Git Bash
git clone https://github.com/ADC1920/AI-short-play-video-creation.git ~/.agents/skills/ai-short-play-video-creation

# Windows PowerShell
git clone https://github.com/ADC1920/AI-short-play-video-creation.git "$env:USERPROFILE\.agents\skills\ai-short-play-video-creation"
```

也可以先克隆到任意位置，再把整个目录复制进技能根（`~/.agents/skills/`、`~/.claude/skills/`，或其他平台的扫描路径）。各场景的触发话术见 SKILL.md 的「触发示例」。

## 脚本自检

九个脚本都带 selftest，改动后逐个跑一遍即可：

```bash
python scripts/validate_storyboard.py --selftest
python scripts/make_grid.py --selftest          # 需要 pip install pillow
python scripts/check_refs.py --selftest
python scripts/init_project.py --selftest
python scripts/archive_old_docx.py --selftest
python scripts/sync_entity.py --selftest
python scripts/check_double_root.py --selftest
python scripts/check_seams.py --selftest          # 需要 pip install numpy pillow；实景抽帧需 ffmpeg（无则自动跳过）
python scripts/fix_table_pagination.py --selftest
```

## License

MIT
