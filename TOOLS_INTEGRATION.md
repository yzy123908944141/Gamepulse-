# GamePulse Tools Integration

本目录已经接入四个可被 Agent 调用的工具包：

1. `agent/vendor_tools/character_tool`
   - 原始包：`character_tool_deploy.zip`
   - Agent 入口：`tools.query_tools.get_character_profiles`
   - 作用：检索已结构化角色档案，返回基本信息、性格、背景、动机和主要关系。
   - 默认数据：`agent/vendor_tools/character_outputs/character_json`
   - 可用环境变量：`GAMEPULSE_CHARACTER_JSON_DIR`

2. `agent/vendor_tools/story_retrieval_tool`
   - 原始包：`story_retrieval_tool_deploy.zip`
   - Agent 入口：`tools.query_tools.rag_search_story`
   - 作用：检索剧情库或内置 Chroma RAG，返回结构化剧情上下文和来源片段。
   - 默认数据：`agent/vendor_tools/story_library`
   - 可用环境变量：`GAMEPULSE_STORY_LIBRARY`、`GAMEPULSE_STORY_RETRIEVER`、`GAMEPULSE_RAG_SCRIPT`、`GAMEPULSE_CHROMA_DIR`、`GAMEPULSE_EMBEDDING_MODEL`、`GAMEPULSE_STORY_SUMMARIZER`

3. `agent/vendor_tools/worldview_tool`
   - 原始包：`gamepulse_worldview_tool_deploy.zip`
   - Agent 入口：`tools.query_tools.get_world_lore_tool`，工具名为 `get_world_lore`
   - 作用：查询 `world.txt` 中明确存在的《鸣潮》世界观事实。
   - 默认数据：`agent/vendor_tools/world_outlook/world.txt`
   - 可用环境变量：`GAMEPULSE_WORLD_PATH`

4. `agent/vendor_tools/risk_card_story_tool`
   - 原始包：`risk_card_story_tool.zip`
   - Agent 入口：`tools.query_tools.search_risk_cards`
   - 作用：查询剧情/角色强相关风险卡摘要。
   - 默认数据库：`D:/program/two-dimensional_game/agent.db`
   - 默认输出目录：`D:/program/two-dimensional_game/record/story_risk_summary`
   - 可用环境变量：`GAMEPULSE_RISK_DB`、`GAMEPULSE_RISK_OUTPUT_DIR`、`GAMEPULSE_RISK_SCRIPT`

## Chroma RAG 配置示例

```powershell
$env:GAMEPULSE_STORY_RETRIEVER="chroma-rag"
$env:GAMEPULSE_RAG_SCRIPT="D:/program/GamePulse/rag/rag_query.py"
$env:GAMEPULSE_CHROMA_DIR="D:/program/GamePulse/rag/chroma_db"
$env:GAMEPULSE_EMBEDDING_MODEL="D:/program/GamePulse/rag/models/bge-m3"
$env:GAMEPULSE_STORY_SUMMARIZER="mock"
```

注意：如果本地 `bge-m3` embedding 模型不存在，Chroma RAG 会在检索阶段失败，此时还不会调用 DeepSeek API。

## Agent 挂载位置

- `tools/query_tools.py`：四个工具的 LangChain 适配层。
- `agent/review_agents.py`：角色 Agent 和剧情 Agent 的工具列表。
- `tools/__init__.py`：工具导出入口。





## 内置 Chroma RAG 说明

当前项目已内置剧情 RAG 脚本和 Chroma 数据库：

- RAG 脚本：`D:/program/GamePulse/rag/rag_query.py`
- Chroma persist 目录：`D:/program/GamePulse/rag/chroma_db/chroma_db`
- 数据量验证：`rag_query.py --stats` 可读取到 7542 条剧情切片

语义检索还需要本地 embedding 模型 `bge-m3`。模型不随本次文件复制自动生成，请放到：

```powershell
D:/program/GamePulse/rag/models/bge-m3
```

也可以通过环境变量指定：

```powershell
$env:GAMEPULSE_EMBEDDING_MODEL="你的/bge-m3/模型路径"
```

如果未找到 `bge-m3`，`rag_search_story` 默认回退到项目内关键词剧情库，避免总控 Agent 因模型缺失中断；如果手动设置 `GAMEPULSE_STORY_RETRIEVER="chroma-rag"`，则必须保证模型目录可用。

