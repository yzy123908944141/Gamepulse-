# GamePulse 环境依赖说明

本文记录 GamePulse 当前可独立运行所需的环境依赖，并区分“运行依赖”和“数据灌入/重建依赖”。

## 1. Python 运行环境

推荐 Python 3.10+。

当前部署版使用项目内虚拟环境：

```text
D:/program/GamePulse-ultimate/GamePulse/.venv
```

部署到新机器时，可以重新创建虚拟环境：

```powershell
cd D:/program/GamePulse-ultimate/GamePulse
python -m venv .venv
.venv/Scripts/python.exe -m pip install -U pip
.venv/Scripts/python.exe -m pip install -r requirements_backend.txt
```

## 2. 后端运行依赖

基础运行依赖见：

```text
requirements_backend.txt
```

当前包括：

```text
fastapi
uvicorn
pydantic
python-dotenv
sqlalchemy
langchain
langchain-classic
langchain-core
langchain-openai
langgraph
requests
jsonschema
chromadb
```

这些依赖足够支撑：

- FastAPI 后端
- 前端静态页面服务
- 总控 Agent
- 角色/剧情/世界观/舆情 Tools
- SQLite 数据库读取
- 舆情报告导出
- 已有 Chroma 数据库读取能力

## 3. 环境变量

项目根目录使用 `.env`：

```text
DEEPSEEK_API_KEY=你的 Key
OPENAI_API_KEY=同上
LLM_API_KEY=同上
OPENAI_BASE_URL=https://api.deepseek.com
LLM_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
DEEPSEEK_MODEL=deepseek-chat
LLM_MODEL=deepseek-chat
```

正式打包或提交时，不建议携带真实 Key，可改用 `.env.example` 或部署平台环境变量。

## 4. 数据库依赖

公开代码仓库不包含运行数据库；取得有权使用的数据后，将两份数据库放在：

```text
data/raw_data.db
data/agent.db
```

默认不再跨目录读取 `two-dimensional_game`。详细接入步骤见 `DATA_ASSETS_SETUP.md`。如需替换数据库路径，可设置：

```powershell
$env:GAMERPULSE_RAW_DATA_DB="你的/raw_data.db"
$env:GAMERPULSE_AGENT_DB_PATH="你的/agent.db"
```

## 5. RAG 数据与 bge-m3 模型说明

项目已内置 Chroma 剧情库：

```text
rag/rag_query.py
rag/chroma_db/chroma_db
```

其中 Chroma 数据库已经包含剧情切片，当前验证数据量为 7542 条。

`bge-m3` embedding 模型不是 GamePulse 日常运行必需项。它主要用于：

- 首次数据灌入
- 新增剧情资料后的向量化
- 重建 Chroma 索引
- 强制启用 Chroma 语义检索时的查询向量编码

如果只是运行当前前端、后端、Agent、舆情报告和已有结构化数据，不需要把 `bge-m3` 放入主部署包。

如后续需要重建向量库，推荐放置路径：

```text
rag/models/bge-m3
```

或通过环境变量指定：

```powershell
$env:GAMEPULSE_EMBEDDING_MODEL="你的/bge-m3/模型路径"
```

当前代码策略：

- 找到 `rag/models/bge-m3` 时，可启用 Chroma RAG。
- 找不到模型时，`rag_search_story` 默认回退到项目内关键词剧情库，避免 Agent 运行中断。
- 如果手动设置 `GAMEPULSE_STORY_RETRIEVER=chroma-rag`，则必须保证模型路径可用。

## 6. 数据灌入/预处理可选依赖

舆情预处理组件位于：

```text
data/analysis
data/crawler
```

如果只使用已有数据库和报告功能，不需要额外操作。

如果要重新爬取、清洗、AI 分析评论，可能还需要根据实际爬虫和模型调用情况补充：

```text
beautifulsoup4
lxml
pandas
schedule
sentence-transformers
```

其中 `sentence-transformers` 和 `bge-m3` 只在 embedding/向量化相关流程中需要。

## 7. 启动命令

```powershell
cd D:/program/GamePulse-ultimate/GamePulse
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000/frontend/
```

