# GamePulse 使用与部署说明

GamePulse 是一个面向游戏项目的情报分析与剧本辅助工作台。此版本由 FastAPI 提供后端接口和静态前端页面，使用 SQLite 保存角色、评论、分析结果和聊天记录，并通过 OpenAI 兼容接口调用 DeepSeek 等大模型。本项目为2024级nku的暑期实训项目，主要为参考价值的demo

本文面向首次运行、API 配置、数据库迁移和常见故障排查。默认项目目录为 `D:\program\GamePulse-ultimate\GamePulse`；如果项目移动到其他位置，请以实际路径替换示例。

**公开仓库仅上传代码与文档。**数据库、评论、Chroma 索引和角色立绘需在本机另行接入，操作见 [DATA_ASSETS_SETUP.md](DATA_ASSETS_SETUP.md)。本地完整版可能已有这些文件，但不能据此假定新克隆的仓库也包含它们。

## 1. 功能概览

- 角色目录、角色详情、评分、风险警告、关键词和个人故事展示。
- 按分析结果追溯关联评论，查看评论平台、内容和来源链接。
- 剧情/角色情报 Agent 对话，支持总控 Agent 调用子 Agent 和工具。
- 舆情报告导出、数据库摘要展示和舆情预处理接口。
- 本地剧情资料检索；在配置好本地 RAG 数据与 embedding 模型后可启用 Chroma 语义检索。

注意：页面和数据库功能可以在没有模型 API Key 时启动，但聊天等需要 LLM 的功能无法正常生成回答。

## 2. 目录结构

```text
GamePulse/
  main.py                         FastAPI 应用入口
  启动GamePulse.bat                Windows 一键启动脚本
  requirements_backend.txt         Python 后端依赖
  .env.example                    环境变量模板，不含可用密钥
  .env                            本机配置，需自行创建，不要分享或提交
  data/
    raw_data.db                   本机自行接入：角色、评论和 URL
    agent.db                      本机自行接入：评分、风险与评论关联
  agent/                          Agent、Prompt、记忆和工具
  tools/                          API 适配、舆情报告和预处理工具
  rag/                            RAG 查询代码；索引和模型需本机接入
  frontend_assistant_yellow_white/
    frontend_yellow_white_fastapi_package_20260729/
                                  FastAPI 静态前端；立绘需本机接入
  reports/                        报告输出目录
  .venv/                          首次启动自动创建的 Python 虚拟环境
```

不要单独移动 `main.py`、`agent`、`tools` 或前端目录；它们之间通过项目相对路径关联。

## 3. 系统要求

- Windows 10/11。
- Python 3.10 或更高版本；若某个依赖在较新 Python 版本上无法安装，建议使用 Python 3.11 或 3.12 后重新创建虚拟环境。
- 首次启动需要网络下载 Python 依赖。
- 调用在线模型需要能访问对应模型服务的网络，以及有效 API Key。
- 默认本地服务地址为 `http://127.0.0.1:8000`。

## 4. 首次启动

### 方式 A：双击启动

双击项目根目录中的 `启动GamePulse.bat`。脚本会：

1. 从 `.bat` 文件所在目录定位项目根目录，不依赖固定的 `D:\program\GamePulse` 路径。
2. 若项目内没有 `.venv`，创建虚拟环境并安装 `requirements_backend.txt` 中的依赖。
3. 检查现有虚拟环境的依赖；发现缺失时尝试补装。
4. 启动 FastAPI，并在浏览器打开前端页面。

首次依赖安装可能需要几分钟。保持命令行窗口开启；关闭窗口会停止服务。

### 方式 B：PowerShell 手动启动

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements_backend.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

如果 `.venv` 已存在，不需要再次创建。修复缺失依赖时可执行：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m pip install -r requirements_backend.txt
.\.venv\Scripts\python.exe -m pip check
```

### 访问地址

- 前端：<http://127.0.0.1:8000/frontend/>
- 健康检查：<http://127.0.0.1:8000/health>
- API 文档：<http://127.0.0.1:8000/docs>
- 根状态：<http://127.0.0.1:8000/>

## 5. 大模型 API 配置

### 配置文件位置

在 `main.py` 同一层创建 `.env`，即：

```text
D:\program\GamePulse-ultimate\GamePulse\.env
```

可以将 `.env.example` 复制为 `.env`，然后将占位文字替换为自己的密钥。不要把真实密钥写进 Python 代码、README、截图、聊天记录或公开仓库。密钥泄漏后应立即在服务商控制台撤销并重新生成。

### DeepSeek 示例

```dotenv
DEEPSEEK_API_KEY=填入你自己的DeepSeek_API_Key
OPENAI_API_KEY=填入你自己的DeepSeek_API_Key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
DEEPSEEK_MODEL=deepseek-chat
GAMEPULSE_RISK_DB=data/agent.db
GAMEPULSE_RISK_OUTPUT_DIR=reports/story_risk_summary
```

`OPENAI_API_KEY` 和 `DEEPSEEK_API_KEY` 可以填写同一个密钥。当前聊天主链优先读取 `OPENAI_API_KEY`，若未设置则回退到 `DEEPSEEK_API_KEY`；配置 `DEEPSEEK_API_KEY` 且未设置 Base URL 时，代码会默认使用 DeepSeek 地址。推荐仍按上例显式设置，便于排错。

配置其他 OpenAI-compatible 服务时，按服务商要求替换：

- `OPENAI_API_KEY`：服务商签发的 API Key。
- `OPENAI_BASE_URL`：兼容接口的根地址。不同服务商可能要求带 `/v1`，请以其官方文档为准；DeepSeek 示例使用 `https://api.deepseek.com`。
- `OPENAI_MODEL`：该服务商实际支持的模型 ID。
- `GAMEPULSE_RISK_DB`：独立风险卡工具读取的数据库；打包版建议指向项目内的 `data/agent.db`，避免使用旧电脑上的固定盘符路径。
- `GAMEPULSE_RISK_OUTPUT_DIR`：风险卡文件输出目录；相对路径按启动时项目目录解析。

`.env` 文件不要写成 `.env.txt`。使用记事本保存时选择“所有文件”，并确认文件名恰好为 `.env`。等号两侧不要留空格；密钥通常不需要额外引号。

### 哪些功能需要 API

- 角色、数据库摘要、关联评论读取等本地数据库页面不依赖模型 API。
- 助手聊天、Agent 分析和依赖模型的总结功能需要有效的 API Key、模型名和网络连接。
- 风险卡的独立压缩/分析脚本使用 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；这组变量与主聊天配置分开。仅使用网页聊天时通常不需要另设 `LLM_*`。
- API Key 只保存在本机 `.env` 或安全的环境变量中。不要把 `.env` 打包发给他人。

### API 调用成本与隐私

在线模型请求会把对应提示词、用户输入以及工具检索出的上下文发送给服务商。请勿提交不应离开本机的个人信息、未公开内容或密钥。模型调用可能产生费用，并受账户额度、速率限制和服务可用性影响。

## 6. 数据库配置

默认数据库按项目相对路径读取，但公开仓库**不包含数据库文件**。取得有权使用的数据库后，参照 [接入指南](DATA_ASSETS_SETUP.md) 放入：

```text
data/raw_data.db
data/agent.db
```

其中 `raw_data.db` 提供角色基础资料与原始评论；`agent.db` 提供 `analysis_results` 等分析结果。接口用 `character_id` 关联两库中的角色记录。向特定合作方私下交付数据前，应确认授权范围并使用合适的传输方式。

可以在 `.env` 中覆盖默认路径：

```dotenv
GAMERPULSE_RAW_DATA_DB=D:/somewhere/raw_data.db
GAMERPULSE_AGENT_DB_PATH=D:/somewhere/agent.db
```

路径可以使用 Windows 盘符路径或正斜杠。替换数据库前先停止服务并备份原文件。不要在服务运行时用 Excel、SQLite 编辑器或文件同步工具直接覆盖数据库，以免产生锁或损坏。

### SQLite WAL 文件

服务运行时可能出现 `agent.db-wal`、`agent.db-shm`、`raw_data.db-wal`、`raw_data.db-shm`。它们是 SQLite 的运行时文件，不是多余垃圾。服务停止后 SQLite 会按需处理这些文件；不要在服务运行时手动删除。

## 7. 剧情 RAG（可选）

项目可使用本地剧情库进行关键词检索；Chroma 语义检索需要对应的 Chroma 数据、查询脚本和 embedding 模型。缺少模型时不应误以为在线聊天 API Key 能代替本地 embedding 模型。

常用变量：

```dotenv
GAMEPULSE_STORY_RETRIEVER=keyword
GAMEPULSE_RAG_SCRIPT=
GAMEPULSE_CHROMA_DIR=
GAMEPULSE_EMBEDDING_MODEL=
```

只有已准备好本地模型、索引和路径时，才将检索模式设为 `chroma-rag` 并填写相应路径。模型目录缺失时建议保持 `keyword`，避免 RAG 查询失败。路径示例和数据重建说明见 `ENVIRONMENT_REQUIREMENTS.md` 及 `agent/vendor_tools/README.md`。

## 8. 常用 API

在 `/docs` 可交互测试接口。主要接口如下：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 检查服务是否运行 |
| `GET` | `/api/db/summary` | 查看数据库文件和表摘要 |
| `GET` | `/api/characters` | 获取角色目录 |
| `GET` | `/api/diagnosis?character_id=1` | 获取角色评分、风险、关键词和个人故事 |
| `GET` | `/api/comments/trace?ids=1,2` | 按评论 ID 追溯评论和来源链接 |
| `GET` | `/api/report/export` | 导出舆情报告；可选 `character_id`、`days` 参数 |
| `POST` | `/sessions` | 创建助手会话 |
| `POST` | `/chat` | 发送一次助手请求 |
| `POST` | `/chat/stream` | 以 NDJSON 流式接收助手事件 |
| `POST` | `/api/sentiment/preprocess` | 执行指定的舆情预处理步骤 |

`/api/sentiment/preprocess` 支持导入 CSV、评论分析、聚合和清理等选项。运行前先阅读 `data/README_SENTIMENT_PREPROCESS.md`，特别谨慎使用 `clear_existing`，并备份数据库。

### 创建并发送聊天请求示例

```powershell
$session = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/sessions" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ character_id = 1; title = "测试会话" } | ConvertTo-Json)

$body = @{
  session_id = $session.session_id
  message = "请分析这个角色可能存在的剧情风险"
  shared_context = @{}
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

## 9. 常见问题排查

### 双击后提示找不到 `main.py`

确认正在运行项目根目录里的 `启动GamePulse.bat`，并且它与 `main.py` 位于同一目录。脚本现在根据自身位置定位，不要求项目一定放在某个固定盘符。

### `ModuleNotFoundError: No module named 'xxx'`

使用项目虚拟环境安装依赖，不要误用系统 Python：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m pip install -r requirements_backend.txt
.\.venv\Scripts\python.exe -m pip check
```

报错模块来自独立包时，也要确认该包已列入 `requirements_backend.txt`。不要只在系统 Python 中执行 `pip install`。

### `401`、`invalid_api_key` 或模型认证失败

检查 `.env` 是否位于项目根目录、文件名是否正确、Key 是否完整、是否已被服务商撤销，以及 `OPENAI_API_KEY` 是否意外覆盖了正确的 `DEEPSEEK_API_KEY`。修改 `.env` 后重启服务。

### `404`、模型不存在或接口地址错误

核对 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 是否属于同一个服务商。模型名称必须是服务商支持的模型 ID。不要把完整的 `/chat/completions` 路径填到 Base URL，除非服务商文档明确要求。

### 超时、DNS、连接失败或代理问题

确认本机能够访问模型服务域名，检查系统代理/VPN和防火墙。服务在本机启动并不表示模型 API 网络也可访问。可先打开 `/health` 验证本地后端，再单独测试模型服务连通性。

### 前端打不开或显示 404

确认访问地址是 `/frontend/`，不是直接双击 HTML 文件；确认 `frontend_assistant_yellow_white/frontend_yellow_white_fastapi_package_20260729` 目录存在。FastAPI 仅在该静态目录存在时挂载页面。

### 角色列表为空、评论不存在或数据库报错

先访问 `/api/db/summary` 查看后端实际读取的数据库路径及表信息；确认两份数据库存在、schema 与当前代码兼容，且 `characters`、`analysis_results`、`raw_comments` 等表有数据。更换数据库后重启服务。

### 端口 8000 被占用

关闭旧的 GamePulse 命令窗口或占用端口的程序，再启动。当前启动脚本检测到 8000 已监听时会直接打开页面；如果占用者不是 GamePulse，需先释放端口，或修改启动脚本中的 `PORT` 并同步使用新地址。

### `.env` 修改后仍像没有生效

停止并重新启动 FastAPI。不要在已经运行的服务上期待 `.env` 自动热加载。也检查环境变量是否已由 Windows 用户设置或启动终端预先设置；进程环境变量可能优先于 `.env` 中的值。

## 10. 安全与交付检查

- 不要将真实 `.env`、API Key、访问令牌或私人数据提交到 Git 或打包给他人。
- `.env.example` 仅保留占位值；交付前检查压缩包和 Git 暂存内容。
- `127.0.0.1` 只允许本机访问，适合本地演示。若改为 `0.0.0.0` 对局域网开放，必须先评估认证、访问控制和数据泄露风险；当前演示服务不应直接暴露到公网。
- 用户聊天与分析内容可能写入项目根目录的 `gamerpulse_memory.db`；交付或清理前按数据保留要求处理。
- 运行任何会写数据库的导入、清洗或预处理功能前，先备份 `data/*.db`。

## 11. 维护与验证

启动前可做基础语法检查：

```powershell
cd D:\program\GamePulse-ultimate\GamePulse
.\.venv\Scripts\python.exe -m py_compile main.py agent\orchestrator.py agent\review_agents.py tools\query_tools.py tools\sentiment_report_tool.py
.\.venv\Scripts\python.exe -m pip check
```

服务运行后：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/db/summary"
```

数据、评论、索引和立绘接入见 `DATA_ASSETS_SETUP.md`。Agent、工具和环境说明见 `README_DEPLOY.md`、`ENVIRONMENT_REQUIREMENTS.md`、`TOOLS_INTEGRATION.md` 及 `data/README_SENTIMENT_PREPROCESS.md`。
