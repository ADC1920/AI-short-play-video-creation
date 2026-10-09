# ai-short-play-video-creation · AI 漫剧制作技能

把一句话剧情或完整剧本，变成可执行的漫剧（动态漫）视频工程：分镜蓝图、宫格分镜图、逐镜视频提示词一条龙。适用于 Claude Code / ZCode 等 Agent 的 Skill 机制（SKILL.md + 按需加载的 references）。

## 技能结构

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 三条路线决策、触发示例、铁律与核心公式、平台硬约束、成本与确认纪律、排障速查、多集工作流 |
| `references/agent-prompt.md` | 「短剧分镜架构师」系统提示词全文（可直接粘贴）+ 配套操作流程 + 实战范例 |
| `references/grid-storyboard.md` | 宫格分镜直生：4/6/9/25 宫格 JSON 提示词、后处理链、分镜模板捷径 |
| `references/face-workarounds.md` | 人脸审核规避五法（墨镜遮挡 / 网格遮挡 / 无五官三视图 / 服装+头部组合 / 风格转绘） |
| `references/asset-workflow.md` | 素材资产与一致性工艺：人物锚点法、ref 数量红线、候选图选择制、人工把关清单、ref 库规模标准 |
| `references/frame-industrial.md` | 分镜图工艺：三层分离铁律、镜头级先图后视频、8 段式写法、非人形偏置对策、4 模选档、并发限流 |
| `references/prompt-craft.md` | 提示词进阶：三作用域、末态法则、时间粒度、多素材绑定、模型实测档案 |
| `references/transition-editing.md` | 衔接与后期：转场「剪辑做还是模型做」、编辑四件套、向前/向后延长、接龙 |
| `references/continuity-log.md` | 连续性台账：连续性账 / Take 记录 / 提示词版本账（多集一致性管理） |
| `references/audio-voice.md` | 声音与配音：四轨设计、角色音色表、台词标注、Edge TTS 落地、混音检查 |
| `scripts/validate_storyboard.py` | 分镜 JSON 机检：数量 / 词数 / 字符上限 / 必含排除词（中英兼容）/ 禁用句式 / 编号重复 |
| `scripts/make_grid.py` | 本地拼宫格（4/6/9/25：`--cols 2/3/5`），依赖 Pillow |
| `scripts/check_refs.py` | 素材与 @ 引用核对：断链引用与闲置素材双向报告 |
| `scripts/init_project.py` | 多集项目脚手架：一键生成标准目录结构 |
| `CHANGELOG.md` | 版本记录 |

## 三条路线

- **路线 A 漫剧智能体**：系统提示词 + 剧本 → 工程级分镜蓝图（镜号 / 时长 / 转场 / 声音设计）→ 逐镜生成，尾帧接力保连贯。
- **路线 B 宫格分镜直生**：剧情一句话 → 分镜 JSON（可机检）→ 宫格分镜图 → 一张图直出 15s 连贯片段。
- **路线 C 人脸审核规避五法**：人物参考图被人脸检测拦截时的五种替代方案，各带生成与使用提示词。

另有：多集长剧工作流（分集 → 每集项目目录 → 素材全剧共用，`scripts/init_project.py` 一键建结构）、素材锚点法与 ref 一致性红线（`references/asset-workflow.md`）、分镜图工艺与三层分离（`references/frame-industrial.md`）、提示词进阶工艺（`references/prompt-craft.md`）、转场决策与编辑延长（`references/transition-editing.md`）、多集连续性台账（`references/continuity-log.md`）、声音与配音模块（`references/audio-voice.md`）、台词语速折算与时间轴式提示词、成本与确认纪律（先图后视频两层 / 逐集解锁 / 重生预算）、素材引用核对（`scripts/check_refs.py`）、平台硬约束核对表、故障首修表、首镜 2 秒钩子法则。

## 安装

从 GitHub 克隆仓库到 Agent 的技能根目录（目录名即技能名 `ai-short-play-video-creation`）：

```bash
# Linux / macOS / Git Bash
git clone https://github.com/ADC1920/AI-short-play-video-creation.git ~/.agents/skills/ai-short-play-video-creation

# Windows PowerShell
git clone https://github.com/ADC1920/AI-short-play-video-creation.git "$env:USERPROFILE\.agents\skills\ai-short-play-video-creation"
```

也可以先克隆到任意位置，再把整个 `ai-short-play-video-creation/` 目录复制到技能根目录（`~/.agents/skills/`、`~/.claude/skills/` 或其他平台的技能扫描路径）。触发话术示例见 SKILL.md 的「触发示例」一节。

## 脚本自检

```bash
python scripts/validate_storyboard.py --selftest
python scripts/make_grid.py --selftest          # 需要 pip install pillow
python scripts/check_refs.py --selftest
python scripts/init_project.py --selftest
```

## License

MIT
