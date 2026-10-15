# ai-short-play-video-creation · AI 短剧创作工作流

把剧本或一句剧情梗概做成 AI 短剧视频。覆盖分镜、素材、逐镜生成、配音和后期拼接，动态漫、漫剧、写实风都适用，出片以即梦 Seedance 为主。整套技能按 Agent Skill 机制组织，Claude Code、ZCode、Codex 等可以直接安装使用。

## 三条路线

- **路线 A**，分镜智能体。有完整剧本时用：把系统提示词贴进对话助手，得到工程级分镜蓝图（镜号、时长、转场、声音设计），再逐镜出图、出视频。
- **路线 B**，宫格分镜直生。只有一句话梗概时用：生成分镜 JSON（可机检），拼成宫格分镜图，一张图直出 15 秒片段。
- **路线 C**，人脸审核规避。人物参考图被人脸检测拦截时的五种做法，可以叠加在 A、B 上。

长剧和小说改编走多集工作流：先分集，再逐集套用 A 或 B，素材全剧共用一套。剧本之外还有几块常用工艺，比如多人戏站位与轴线、打戏预演、微表情、情绪节拍与开场钩子、参考视频对标、段缝衔接，入口都在下表。写提示词之前，建议先过一遍 SKILL.md 的铁律与核心公式。

## 技能结构

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 主入口：三条路线、对标参考流程、铁律与核心公式、平台硬约束、成本与确认纪律、排障速查、多集工作流 |
| `references/agent-prompt.md` | 「短剧分镜架构师」系统提示词全文（可直接粘贴）+ 操作流程 + 实战范例 |
| `references/grid-storyboard.md` | 宫格分镜直生：4/6/9/25 宫格 JSON 提示词、后处理链 |
| `references/face-workarounds.md` | 人脸审核规避五法：墨镜遮挡 / 网格遮挡 / 无五官三视图 / 服装+头部组合 / 风格转绘 |
| `references/asset-workflow.md` | 素材与一致性：人物锚点法、ref 数量红线、候选图选择制、首帧重构图规范 |
| `references/frame-industrial.md` | 分镜图工艺：三层分离、镜头级先图后视频、8 段式写法、非人形偏置对策 |
| `references/prompt-craft.md` | 提示词进阶：三作用域、末态法则、时间粒度与词锚定、否定失效三改法、模型实测档案 |
| `references/transition-editing.md` | 衔接与后期：转场决策、编辑与延长、接龙、成片机检三查、工具路线对照 |
| `references/continuity-log.md` | 连续性台账：连续性账、段缝衔接、场景出场记录、Take 记录 |
| `references/audio-voice.md` | 声音与配音：四轨设计、角色音色表、台词标注、Edge TTS 落地、混音检查 |
| `references/jimeng-seedance-2.5.md` | 即梦 Seedance 2.5 规则与限制（CLI 实查）：能力规格、素材上限、积分参考、审核限制 |
| `references/facs-micro-expression.md` | 面部表演：微表情四区写法、真假笑、强度三档与起-hold-落、常用情绪配方 |
| `references/emotion-beat-curve.md` | 情绪节拍与开场钩子：12 节拍曲线体检表、钩子模式库、2 秒结构模板 |
| `references/action-previs.md` | 打戏预演：R1-R3 强度档、15 秒完播结构、11 环动力链、镜头五要素 |
| `scripts/validate_storyboard.py` | 分镜 JSON 机检：数量、词数、字符上限、排除词、禁用句式、编号重复、告警；门日志 `--stats` |
| `scripts/make_grid.py` | 本地拼宫格（4/6/9/25），依赖 Pillow |
| `scripts/check_refs.py` | 素材与 @ 引用核对：断链（Error）、待补标注（Warning）、闲置素材（Warning）；`--bindings` 绑定自检 |
| `scripts/init_project.py` | 多集项目脚手架，一键生成标准目录结构 |
| `scripts/archive_old_docx.py` | docx 交付版本管理：旧版移入 `_旧版归档/`，支持 `--dry-run` 预览 |
| `scripts/sync_entity.py` | 技能实体同步：备份、差异扫描、md5 复核一条链 |
| `scripts/check_double_root.py` | 双根部署核对与补链：内容与硬链逐件检查，只修「内容相同非硬链」 |
| `scripts/check_seams.py` | 成片接缝质量量化检测：相邻分镜尾帧/首帧的四维色差指标与综合偏差排序 |
| `scripts/fix_table_pagination.py` | docx 分页修复：表格行不跨页、标题防孤行、操作顺序段防切半 |
| `CHANGELOG.md` | 版本记录 |

## 快速上手

1. **有剧本**：走路线 A。把 `references/agent-prompt.md` 里的系统提示词贴进对话助手，输入剧本，得到分镜蓝图，再按蓝图逐镜执行。
2. **只有一句话**：走路线 B。生成宫格分镜 JSON，用 `python scripts/make_grid.py -o grid.png <图片目录>` 拼成宫格图，再直出视频。
3. **工程工具**：素材引用核对 `python scripts/check_refs.py <项目目录>`，分镜 JSON 机检 `python scripts/validate_storyboard.py <story.json>`，多集项目建目录 `python scripts/init_project.py <项目目录> --episodes 12`。
4. **样例项目**：`examples/demo-multi-ep/` 是一个最小多集样例，带占位素材、剧本和分镜 JSON。可以拿来参照，也用作回归测试，命令见该目录的 README。push 时 GitHub Actions 会自动跑九个脚本的自检，加上样例项目的端到端回归。

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
