# 演示样例项目（demo-multi-ep）

最小可跑的多集项目结构示例，两个用途：

1. **快速上手参照**：对照 `第1集/` 的三件结构与根 `素材/` 的命名约定（文件名即引用名）。
2. **回归夹具**：CI（`.github/workflows/selftest.yml`）对它跑端到端检查——`check_refs.py` 应无断链、`validate_storyboard.py` 应 PASS。改动脚本后本地也可照跑：

```bash
python scripts/check_refs.py examples/demo-multi-ep
python scripts/validate_storyboard.py "examples/demo-multi-ep/第1集/分镜/sb.json" --no-log
```

说明：素材目录里是占位色块图（非真实参考图），仅用于引用核对；分镜 JSON 是中文提示词的合法样例（无时间码/无字幕排除词齐全）。本目录为仓库级质量资产，不入本机技能实体。
