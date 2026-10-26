# GamePulse 部署使用说明

本包是 GamePulse Agent 工作台的项目代码，不包含 Python 虚拟环境。公开代码仓库也不包含数据库、评论、RAG 索引和角色立绘；请先阅读 [README.md](README.md) 和 [DATA_ASSETS_SETUP.md](DATA_ASSETS_SETUP.md)。

## 目录说明

```text
GamePulse/
  main.py                         # FastAPI 入口
  agent/                          # 总控、角色审查、剧情审查 Agent
    orchestrator.py               # 总控 Agent
    review_agents.py              # 子 Agent 与工具挂载
    chains/                       # 角色/剧情链路代码
    prompts/                      # 总控、角色审查、剧情审查 prompt
    vendor_tools/                 # 世界观、角色档案、剧情检索、风险卡工具包
  tools/                          # GamePulse 工具适配层
    query_tools.py                # 角色/剧情/世界观/风险卡工具
    sentiment_report_tool.py      # 舆情报告与红线/趋势/槽点查询
    generate_sentiment_report_md.py
  reports/                        # 生成的舆情报告示例
  TOOLS_INTEGRATION.md            # 工具接入说明
```

## 运行环境

推荐使用项目目录内的虚拟环境。双击 `启动GamePulse.bat` 会在首次运行时自动创建 `.venv` 并安装后端依赖；也可以手动执行：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_backend.txt
```

虚拟环境位于项目自身目录，不依赖 `D:\program\venv` 或 Downloads 中的依赖文件。启动脚本会检查环境；如果发现依赖缺失，会按 `requirements_backend.txt` 自动补装。

已验证的关键依赖包括：

```text
fastapi
uvicorn
langchain
langchain-openai
langgraph
chromadb
sentence-transformers
torch
```

## API Key 配置

启动前设置 DeepSeek / OpenAI-compatible 环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:OPENAI_API_KEY=$env:DEEPSEEK_API_KEY
$env:OPENAI_BASE_URL="https://api.deepseek.com"
$env:OPENAI_MODEL="deepseek-chat"
$env:DEEPSEEK_MODEL="deepseek-chat"
$env:PYTHONIOENCODING="utf-8"
```

不要把 API Key 写入代码或 README。

## 启动服务

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

也可以双击项目根目录下的 `启动GamePulse.bat`；启动脚本会自动定位项目目录并打开前端页面。

浏览器访问：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
```

健康检查：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

## 基本接口

### 创建会话

```powershell
$body = @{
  character_id = 1
  title = "测试会话"
  current_text = ""
  selected_constraints = @()
  custom_constraint = $null
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/sessions" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

### 发送 Agent 请求

```powershell
$body = @{
  session_id = 1
  message = "请审查新角色替代秧秧陪漂泊者调查云陵谷的风险。"
  shared_context = @{}
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

如果 PowerShell 显示中文乱码，可用 Python 客户端请求并按 UTF-8 解码。

## 已接入 Agent

### 总控 Agent

Prompt 文件：

```text
agent/prompts/control_agent.txt
```

职责：

- 理解用户意图
- 决定是否调用角色审查 Agent、剧情审查 Agent 或舆情工具
- 整合最终输出

### 角色审查 Agent

Prompt 文件：

```text
agent/prompts/character_prompt.txt
```

职责：

- 角色设定
- OOC
- 撞人设/撞身份/撞动机
- 角色台词与行为合理性
- 角色招黑与舆情风险

### 剧情审查 Agent

Prompt 文件：

```text
agent/prompts/plot_prompt.txt
```

职责：

- 剧情结构
- 剧情承接
- 章节安排
- 桥段推进
- 伏笔铺垫与回收
- 世界观冲突

## 已接入工具

### 角色档案

入口：

```python
tools.query_tools.get_character_profiles
```

默认数据：

```text
agent/vendor_tools/character_outputs/character_json
```

### 世界观检索

入口：

```python
tools.query_tools.get_world_lore_tool
```

默认数据：

```text
agent/vendor_tools/world_outlook/world.txt
```

### 剧情检索

入口：

```python
tools.query_tools.rag_search_story
```

默认本地剧情库：

```text
agent/vendor_tools/story_library
```

可选 Chroma RAG 环境变量：

```powershell
$env:GAMEPULSE_STORY_RETRIEVER="chroma-rag"
$env:GAMEPULSE_RAG_SCRIPT="D:/program/GamePulse-ultimate/GamePulse/rag/rag_query.py"
$env:GAMEPULSE_CHROMA_DIR="D:/program/GamePulse-ultimate/GamePulse/rag/chroma_db/chroma_db"
$env:GAMEPULSE_EMBEDDING_MODEL="D:/program/GamePulse-ultimate/GamePulse/rag/models/bge-m3"
```

注意：只有手动强制启用 Chroma 语义检索、数据灌入或重建索引时才需要本地 embedding 模型，例如 `bge-m3`；日常运行可回退关键词检索。

### 风险卡

入口：

```python
tools.query_tools.search_risk_cards
tools.query_tools.refresh_story_risk_cards
```

默认数据库：

```text
data/agent.db
```

### 舆情报告

入口：

```python
tools.sentiment_report_tool.generate_sentiment_report
tools.sentiment_report_tool.generate_sentiment_report_tool
tools.sentiment_report_tool.get_red_lines_tool
tools.sentiment_report_tool.get_top_complaints_tool
tools.sentiment_report_tool.get_sentiment_trend_tool
```

默认数据库：

```text
data/raw_data.db
data/agent.db
```

生成 Markdown 舆情报告：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe tools\generate_sentiment_report_md.py
```

输出：

```text
reports/全部舆情报告.md
```

## 注意事项

1. 本部署包不包含虚拟环境；首次启动会在项目目录内创建 `.venv`。
2. 公开仓库不含 `data/raw_data.db` 和 `data/agent.db`；需要有权使用的数据时请在本机单独接入。
3. 本部署包不包含 API Key。
4. `gamerpulse_memory.db` 是本地会话运行时数据库，会在使用会话功能后创建。
5. LLM 请求会将对应输入和检索上下文发送给模型服务商，使用真实评论前应确认数据处理权限。

## 快速自检

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m py_compile main.py agent\orchestrator.py agent\review_agents.py tools\query_tools.py tools\sentiment_report_tool.py
```

启动后：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```


## 前端助手页面

前端页面位于：

```text
frontend_assistant_yellow_white/frontend_yellow_white_fastapi_package_20260729
```

GamePulse 后端会在目录存在时自动挂载静态页面：

```text
http://127.0.0.1:8000/frontend/
```

助手页已经接入总控 Agent：首次提问自动创建 `/sessions`，随后调用 `/chat`，并在回复下方显示 `called_agents` 与 `called_tools`，用于调试和审计工具调用链。

当前仅保留黄白工业风前端。推荐直接通过 FastAPI 访问：

```text
http://127.0.0.1:8000/frontend/
```

如需单独查看前端源码，目录为：

```text
frontend_assistant_yellow_white/frontend_yellow_white_fastapi_package_20260729
```

### 推荐一键启动脚本

推荐使用项目根目录下的 `启动GamePulse.bat`。也可在 PowerShell 中手动启动：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

API Key 和 `.env` 配置说明见项目根目录 `README.md`。

## 实时调用链路展示

助手页现在优先调用 `POST /chat/stream`。该接口以 NDJSON 流式返回运行状态，前端会在最终回答生成前展示类似下面的过程：

```text
1. 准备 · request：已收到请求，正在启动总控 Agent
2. 进入子 Agent · orchestrator：总控 Agent 正在判断调用路径
3. 调用 Tool · get_red_lines
4. Tool 返回 · get_red_lines
5. 完成子 Agent · orchestrator：总控 Agent 已完成整合
```

说明：这里展示的是可审计的 Agent/Tool 调用链路，不是模型内部隐藏推理。最终回答仍会显示 `called_agents` 与 `called_tools` 汇总。


当前使用黄白前端包：frontend_assistant_yellow_white/frontend_yellow_white_fastapi_package_20260729。


## 本地数据库说明

后端默认从项目内 `data/raw_data.db`、`data/agent.db` 读取，但公开仓库不提供数据库。请参照 `DATA_ASSETS_SETUP.md` 在本机接入；也可设置 `GAMERPULSE_RAW_DATA_DB` 和 `GAMERPULSE_AGENT_DB_PATH` 覆盖路径。



## 内置 Chroma RAG 说明

当前项目已内置剧情 RAG 脚本和 Chroma 数据库：

- RAG 脚本：`rag/rag_query.py`
- Chroma persist 目录：`rag/chroma_db/chroma_db`
- 数据量验证：`rag_query.py --stats` 可读取到 7542 条剧情切片

`bge-m3` embedding 模型不属于 GamePulse 日常运行必需项，主要用于数据灌入、新增剧情资料后的向量化、重建 Chroma 索引，或手动强制启用 Chroma 语义检索时的查询向量编码。

如果只是运行当前前端、后端、Agent、舆情报告和已有结构化数据，不需要把 `bge-m3` 放入主部署包。

如后续需要重建向量库，推荐放置路径：

```powershell
rag/models/bge-m3
```

也可以通过环境变量指定：

```powershell
$env:GAMEPULSE_EMBEDDING_MODEL="你的/bge-m3/模型路径"
```

如果未找到 `bge-m3`，`rag_search_story` 默认回退到项目内关键词剧情库，避免总控 Agent 因模型缺失中断；如果手动设置 `GAMEPULSE_STORY_RETRIEVER="chroma-rag"`，则必须保证模型目录可用。

环境依赖的完整分层说明见 `ENVIRONMENT_REQUIREMENTS.md`。

## 舆情预处理组件

已集成到 data/analysis 与 data/crawler，统一入口为 tools.sentiment_preprocess_tool.run_sentiment_preprocess，后端接口为 POST /api/sentiment/preprocess。详细说明见 data/README_SENTIMENT_PREPROCESS.md。




## 一键启动

在 Windows 上可直接双击项目根目录下的 启动GamePulse.bat。脚本会自动设置 UTF-8 环境变量、启动 FastAPI 后端，并打开 http://127.0.0.1:8000/frontend/。运行期间不要关闭该命令行窗口。



