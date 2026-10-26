# GamePulse Agent Vendor Tools

`agent/vendor_tools` 是 GamePulse Agent 的本地工具包目录，用于放置已经封装好的外部 Tool。上层 Agent 不直接读这些包的内部文件，而是通过 `tools/query_tools.py` 中的 LangChain Tool 适配器统一调用。

## 总体接入关系

```text
agent/review_agents.py
  ├─ character_review_tool
  │   ├─ get_character_profiles
  │   ├─ get_world_lore
  │   ├─ search_risk_cards
  │   └─ rag_search_story
  └─ plot_review_tool
      ├─ rag_search_story
      ├─ get_world_lore
      ├─ get_character_profiles
      └─ search_risk_cards

tools/query_tools.py
  └─ agent/vendor_tools/*
```

## 目录结构

```text
agent/vendor_tools/
  character_tool/            # 角色资料结构化与增量扫描 Tool
  character_outputs/         # 已生成的角色 JSON 档案，供 Agent 检索
  story_retrieval_tool/      # 剧情资料检索与结构化概括 Tool
  story_library/             # 默认示例剧情资料库
  worldview_tool/            # 世界观检索 Tool
  world_outlook/world.txt    # 《鸣潮》世界观文档
  risk_card_story_tool/      # 剧情强相关风险卡筛选/摘要脚本
  docs/                      # 各工具原始说明文档
  manifests/                 # Tool Registry manifest
```

## 1. 角色档案 Tool

- 包目录：`agent/vendor_tools/character_tool`
- Agent 入口：`tools.query_tools.get_character_profiles`
- 底层能力：从已结构化角色 JSON 中检索角色基本信息、性格、背景、动机和主要关系。
- 默认数据：`agent/vendor_tools/character_outputs/character_json`
- 数据来源：由 `scan_character_library` 扫描角色库或 SQLite 数据库后生成。

### 适用问题

- 某角色的身份、阵营、职业是什么？
- 某角色性格与当前剧情行为是否一致？
- 两个角色之间已有关系是什么？
- 角色是否存在设定重叠或动机冲突？

### 环境变量

```powershell
$env:GAMEPULSE_CHARACTER_JSON_DIR="D:/program/GamePulse/agent/vendor_tools/character_outputs/character_json"
```

### 直接调用示例

```python
from tools.query_tools import get_character_profiles

print(get_character_profiles.invoke({"query": "秧秧 漂泊者"}))
```

## 2. 剧情检索 Tool

- 包目录：`agent/vendor_tools/story_retrieval_tool`
- Agent 入口：`tools.query_tools.rag_search_story`
- 底层能力：从剧情库或内置 Chroma RAG 中检索相关片段，并输出结构化剧情上下文。
- 默认数据：`agent/vendor_tools/story_library`
- 默认模式：`keyword` 本地关键词检索。

### 适用问题

- 某段剧情发生了什么？
- 某章节的关键事件和冲突是什么？
- 某角色在某段剧情中的作用是什么？
- 剧情评价前需要追溯原始来源片段。

### 环境变量

```powershell
$env:GAMEPULSE_STORY_LIBRARY="D:/program/GamePulse/agent/vendor_tools/story_library"
$env:GAMEPULSE_STORY_RETRIEVER="keyword"
$env:GAMEPULSE_STORY_SUMMARIZER="mock"
```

### 接入内置 Chroma RAG

```powershell
$env:GAMEPULSE_STORY_RETRIEVER="chroma-rag"
$env:GAMEPULSE_RAG_SCRIPT="D:/program/GamePulse/rag/rag_query.py"
$env:GAMEPULSE_CHROMA_DIR="D:/program/GamePulse/rag/chroma_db"
$env:GAMEPULSE_EMBEDDING_MODEL="D:/program/GamePulse/rag/models/bge-m3"
$env:GAMEPULSE_STORY_SUMMARIZER="mock"
```

注意：Chroma RAG 先加载 embedding 模型并检索 Chroma，再调用总结模型。如果本地 `bge-m3` 不存在，会在检索阶段失败，此时不会产生 DeepSeek/OpenAI API 扣费。

### 直接调用示例

```python
from tools.query_tools import rag_search_story

print(rag_search_story.invoke({"query": "漂泊者在云陵谷经历了什么？", "top_k": 3}))
```

## 3. 世界观检索 Tool

- 包目录：`agent/vendor_tools/worldview_tool`
- Agent 入口：`tools.query_tools.get_world_lore_tool`
- LangChain 工具名：`get_world_lore`
- 默认数据：`agent/vendor_tools/world_outlook/world.txt`
- 底层能力：按主题检索《鸣潮》世界观文档中明确存在的内容。

### 适用问题

- 悲鸣、海蚀、残象、声骸是什么？
- 共鸣者、超频、索诺拉相关规则是什么？
- 黑海岸、残星会、岁主、鸣式等设定是什么？
- 剧情审查时需要确认世界观事实边界。

### 使用边界

- 只提供世界观背景资料。
- 不负责角色评价、剧情质量评价或舆情总结。
- 找不到答案时返回未找到，不自行补设定。
- 索诺拉中的内容不一定等同于客观事实。
- 岁主不能简单等同于全知神明。
- 鸣式与普通残象不是同一层级。
- 漂泊者真实身份属于主线谜团，不能擅自下定论。

### 环境变量

```powershell
$env:GAMEPULSE_WORLD_PATH="D:/program/GamePulse/agent/vendor_tools/world_outlook/world.txt"
```

### 直接调用示例

```python
from tools.query_tools import get_world_lore_tool

print(get_world_lore_tool.invoke({"query": "什么是悲鸣？", "max_chars": 1000}))
```

## 4. 剧情风险卡 Tool

- 包目录：`agent/vendor_tools/risk_card_story_tool`
- Agent 查询入口：`tools.query_tools.search_risk_cards`
- Agent 刷新入口：`tools.query_tools.refresh_story_risk_cards`
- 默认数据库：`D:/program/two-dimensional_game/agent.db`
- 默认输出目录：`D:/program/two-dimensional_game/record/story_risk_summary`

### 底层能力

该工具从 `agent.db.analysis_results.risk_warnings` 中筛选剧情/角色强相关风险，再生成风险卡摘要。Agent 默认只查询已经生成的摘要；刷新摘要需要显式调用 `refresh_story_risk_cards`。

### 适用问题

- 玩家是否对某类角色塑造有高频争议？
- 某段剧情是否容易触发 OOC、倒贴、洗白、说教、设定冲突等风险？
- 当前剧情改动是否存在传播或舆情风险？

### 环境变量

```powershell
$env:GAMEPULSE_RISK_DB="D:/program/two-dimensional_game/agent.db"
$env:GAMEPULSE_RISK_OUTPUT_DIR="D:/program/two-dimensional_game/record/story_risk_summary"
$env:GAMEPULSE_RISK_SCRIPT="D:/program/GamePulse/agent/vendor_tools/risk_card_story_tool/compress_risk_titles.py"
```

### 查询示例

```python
from tools.query_tools import search_risk_cards

print(search_risk_cards.invoke({"query": "角色塑造 OOC", "max_results": 5}))
```

### 刷新示例

```python
from tools.query_tools import refresh_story_risk_cards

# 默认不调用 API，只跑小样本检查
print(refresh_story_risk_cards.invoke({"max_items": 20, "run_api": False}))
```

## 推荐运行环境

建议使用已经创建好的虚拟环境：

```powershell
D:/program/venv/Scripts/Activate.ps1
```

关键依赖已验证：

```text
fastapi 0.139.0
langchain_core 1.4.8
chromadb 1.5.9
sentence_transformers 5.6.0
torch 2.12.1+cpu
```

## 常见问题

### 1. `attempt to write a readonly database`

Chroma 打开持久化数据库时可能需要写入维护信息。如果在沙箱或只读目录运行，会出现该错误。解决方式是给 Chroma 目录写权限，或在普通本地终端运行。

### 2. 找不到 `bge-m3`

外部 `rag_query.py` 默认查找：

```text
D:/program/GamePulse/rag/models/bge-m3
```

如果模型不在该路径，请设置：

```powershell
$env:GAMEPULSE_EMBEDDING_MODEL="实际的 bge-m3 本地目录"
```

### 3. API 没扣费

如果流程卡在 Chroma 或 embedding 模型阶段，还没有调用 DeepSeek/OpenAI-compatible 总结模型，所以不会扣费。

### 4. 角色档案为空

确认 `GAMEPULSE_CHARACTER_JSON_DIR` 指向包含 `db_char_*.json` 和 `character_index.json` 的目录。默认目录为：

```text
D:/program/GamePulse/agent/vendor_tools/character_outputs/character_json
```

### 5. 风险卡没有结果

先确认 `D:/program/two-dimensional_game/agent.db` 中是否已经有 `story_risk_summary` 表，或 `record/story_risk_summary` 下是否有 `story_risk_summary_*.json`。如果没有，需要先运行风险卡刷新流程。

## 维护原则

- `agent/vendor_tools` 只放可复用工具和工具数据，不写总控 Agent 编排逻辑。
- Agent 调用入口统一放在 `tools/query_tools.py`。
- 不要让模型编造来源；剧情来源由程序生成或校验。
- 世界观回答只来自 `world.txt`。
- 风险卡工具默认查询已生成摘要，避免每次 Agent 对话都触发大规模 API 调用。



